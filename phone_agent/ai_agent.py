import google.generativeai as genai
from config import GOOGLE_API_KEY
import pandas as pd
from database import conn
import logging

logger = logging.getLogger("ai_agent")

class GeminiPhoneAgent:
    def __init__(self):
        genai.configure(api_key=GOOGLE_API_KEY)
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        self.chat = self.model.start_chat(history=[])
        self.greeting = ""
        self.initialize_chat()

    def initialize_chat(self):
        initial_prompt = """
        You are a vibrant salesman for a customer service department from V-I-T Marketplace. Your task is to assist customers effectively while maintaining a professional, courteous, and concise tone throughout the conversation. Please adhere to the following guidelines:
        - Always write just the phone agent's response in plain english only with punctuation marks. Special characters are strictly not allowed.
        - Greet customers politely.
        - Listen attentively to their concerns and provide clear, solution-oriented responses.
        - You have the store's database connected so query them and don't give wrong answers.
        - You can use your general knowledge to answer relevant questions asked.
        - Ask clarifying questions only when necessary.
        - Avoid long explanations—keep responses brief.
        - Your final target is to convince the user to buy something and close sales.
        - If the customer is satisfied and does not need anything else, conclude the call with a polite farewell and then type 'EXIT' to cut the call.
        - When asked, 'Who are you?', respond: 'I am a person who assists people with their queries.'
        - Understand the customer's sentiments and respond to them accordingly to make them feel valued.

        Ensure that the conversation ends with a professional goodbye before writing 'EXIT' after the customer confirms satisfaction.
        
        Database instructions:
        You are connected to the store's SQL database named 'inventory'. If you need to retrieve any data, start your response with "SQL: " followed by a SELECT query on a single line. DO NOT WRITE ANYTHING ELSE IN THE RESPONSE WHEN YOU SEND A SQL QUERY. You will get back the result as a reply starting with "SQL Response: ". Then you MUST reply to the user in natural conversational language - NEVER send the SQL response data directly to the user. Convert the data into a friendly response.
        
        IMPORTANT: After receiving SQL results, you must:
        1. Read and understand the product data returned
        2. Convert it into a natural, conversational response
        3. NEVER include table data, column names, or technical information in your response to the customer
        4. Speak naturally about the products as a salesperson would
        
        Example conversation flow:
        Customer: "Do you have headphones?"
        Your response: "SQL: SELECT * FROM inventory WHERE \"Product Name\" LIKE '%headphones%' LIMIT 3"
        System returns: "SQL Response: Product Name ... Headphones,Electronics,Boat,1999,120..."
        Your next response: "Yes! We have Boat headphones available for just rupees 1999. They are over-ear wireless headphones with noise cancellation. We have 120 units in stock. Would you like to order one?"
        
        WRONG EXAMPLE - NEVER DO THIS:
        Customer: "Do you have headphones?"
        Your response: "SQL Response: Product Name Category Brand Price in Rupees Stock Description..."
        
        While searching for an item, always search for close matches as exact match may not always be there, but that shouldn't discourage the user from buying. Be a salesman. You can make repeated SQL queries before replying to the user. For example, if you are not sure which category to search for, see the distinct categories of items available, then see the items in relevant categories.
        
        Database Summary:
        This database represents an inventory of products in a store. It contains columns 'Product Name', 'Category', 'Brand', 'Price in Rupees', 'Stock', 'Description'
        
        First Few Lines of Database:
        Product Name,Category,Brand,Price in Rupees,Stock,Description
        Cotton T-Shirt,Clothing,Essentials,299,150,Comfortable cotton t-shirt available in various colors and sizes
        Denim Jeans,Clothing,Levis,1499,75,Classic fit denim jeans with straight leg design
        Running Shoes,Footwear,Nike,2999,45,Lightweight running shoes with cushioned sole
        Wheat Flour,Groceries,Aashirvaad,250,200,Premium quality wheat flour (5kg pack)
        
        You are calling the customer so start with a catchy line for him/her so that he/she wants to buy something. If you think you need to query inventory items then you can do that at the beginning (using "SQL: ") before talking to the user.
        Start with "Hello! This is Alice from V-I-T Market Place, your one-stop destination for amazing deals and top-quality products. We have some exciting offers tailored just for you—may I take a moment to share them?"
        """
        try:
            # Get the initial greeting - handle SQL queries if any
            greeting_response = self.chat.send_message(initial_prompt).text.strip()
            
            # Process any SQL queries in the greeting
            iteration = 0
            max_iterations = 5
            while greeting_response.startswith("SQL:") and iteration < max_iterations:
                iteration += 1
                sql = greeting_response[4:].strip().split('\n')[0]  # Get first line after SQL:
                sql_result = self._execute_sql_and_format(sql)
                greeting_response = self.chat.send_message(sql_result).text.strip()
            
            self.greeting = greeting_response
            logger.info(f"Agent greeting initialized: {self.greeting}")
        except Exception as e:
            logger.exception(f"Error initializing chat: {e}")
            # Fallback greeting
            self.greeting = "Hello! This is Alice from VIT Market Place. May I take a moment to share our offers?"

    def _execute_sql_and_format(self, sql: str) -> str:
        """Execute SQL query and return formatted result"""
        # Allow only SELECT queries for safety
        sql_clean = sql.strip()
        if not sql_clean.lower().startswith("select"):
            logger.warning(f"Non-SELECT query attempted: {sql}")
            return "SQL Response: ERROR: only SELECT queries are allowed."
        
        try:
            df = pd.read_sql_query(sql_clean, conn)
            if df.empty:
                return "SQL Response: No products found matching your criteria."
            
            # Return up to first 10 rows as formatted text
            result = "SQL Response:\n" + df.head(10).to_string(index=False)
            logger.info(f"SQL query executed successfully: {len(df)} rows returned")
            return result
        except Exception as e:
            logger.exception(f"SQL execution error: {e}")
            return f"SQL Response: ERROR: {str(e)}"

    def send(self, message_text):
        """Send message to agent and get response, handling SQL queries automatically"""
        try:
            resp = self.chat.send_message(message_text)
            text = resp.text.strip()
            
            logger.info(f"Agent initial response: {text[:100]}...")
            
            # Keep processing SQL queries until agent gives a normal response
            iteration = 0
            max_iterations = 5  # Prevent infinite loops
            
            while text.startswith("SQL:") and iteration < max_iterations:
                iteration += 1
                # Extract SQL query (first line after SQL:)
                sql_line = text[4:].strip().split('\n')[0]
                logger.info(f"Executing SQL query (iteration {iteration}): {sql_line}")
                
                # Execute SQL and get results
                sql_response = self._execute_sql_and_format(sql_line)
                logger.info(f"SQL result: {sql_response[:200]}...")
                
                # Send SQL results back to agent
                resp = self.chat.send_message(sql_response)
                text = resp.text.strip()
                logger.info(f"Agent response after SQL: {text[:100]}...")
            
            if iteration >= max_iterations:
                logger.warning("Max SQL iterations reached, returning fallback response")
                return "I'm having trouble accessing the product information right now. Could you please rephrase your request?"
            
            # SAFETY CHECK: Make sure agent didn't return raw SQL response
            if text.startswith("SQL Response:"):
                logger.error(f"Agent returned raw SQL response instead of natural language: {text[:200]}")
                return "I found some products but I'm having trouble describing them. Could you ask me about a specific product?"
            
            # Check if response looks like a data dump
            if "Product Name" in text and "Price in Rupees" in text and text.count("\n") > 3:
                logger.error(f"Agent returned database dump instead of natural language: {text[:200]}")
                return "I have that information but I'm having trouble presenting it properly. Could you rephrase your question?"
            
            return text
            
        except Exception as e:
            logger.exception(f"Error in send method: {e}")
            return "Sorry, I'm having trouble processing your request right now. Could you please try again?"
