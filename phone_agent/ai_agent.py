import google.generativeai as genai
from config import GOOGLE_API_KEY
import pandas as pd
from database import conn

class GeminiPhoneAgent:
    def __init__(self):
        genai.configure(api_key=GOOGLE_API_KEY)
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        self.chat = self.model.start_chat(history=[])
        self.greeting = ""
        self.initialize_chat()

    def initialize_chat(self):
        initial_prompt = """
        You are a vibrant salesman for a customer service department from V-I-T Mareketplace. Your task is to assist customers effectively while maintaining a professional, courteous, and concise tone throughout the conversation. Please adhere to the following guidelines:
        - Always write just the phone agent's response in plain english only with punctuation marks. Special characters are strictly not allowed.
        - Greet customers politely.
        - Listen attentively to their concerns and provide clear, solution-oriented responses.
        - You have the store's database connected so query them and don't give wrong answers.
        - You can use your general knowledge to answer relevant questions asked.
        - Ask clarifying questions only when necessary.
        - Avoid long explanations—keep responses brief.
        - You final target is to convince the user to buy something and close sales.
        - If the customer is satisfied and does not need anything else, conclude the call with a polite farewell and then type 'EXIT' to cut the call.
        - When asked, 'Who are you?', respond: 'I am a person who assists people with their queries.'
        - Understand the customer's sentiments and respond to them accordingly to make them feel valued.

        Ensure that the conversation ends with a professional goodbye before writing 'EXIT' after the customer confirms satisfaction.
        
        Database instructions:
        You are connected to the store's sql database named 'inventory'. If you need to retrieve any data, give a one line response: start your response as "SQL: " and send a sql code, and send only one command. DO NOT WRITE ANYTHING ELSE IN THE RESPONSE. You will get back the result as a reply starting with "SQL Response: ". Then you can either reply to the user or make a query again using "SQL: ".
        While searching for item, always search for close matches as exact match may not be always there, but that shouldn't discourage the user from buying. Be a salesman. You can make repeated SQL queries before replying to the user. For example, if you are not sure which category to search for, see the distinct categories of items available, then see the items in relevant categories.
        
        Database Summary:
        This database represents a inventory of products in a store. It contains columns 'Product Name', 'Category', 'Brand', 'Price in Rupees', 'Stock',' Description'
        
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
            self.greeting = self.chat.send_message(initial_prompt).text
        except Exception as e:
            # Fallback greeting
            self.greeting = "Hello! This is Taaniya from VIT Market Place. May I take a moment to share our offers?"

    def _execute_sql_and_format(self, sql: str) -> str:
        # Allow only SELECT queries for safety
        if not sql.strip().lower().startswith("select"):
            return "SQL Response: ERROR: only SELECT queries are allowed."
        try:
            df = pd.read_sql_query(sql, conn)
            if df.empty:
                return "SQL Response: (no rows)"
            # Return up to first 10 rows as CSV-like text
            return "SQL Response: " + df.head(10).to_csv(index=False)
        except Exception as e:
            return f"SQL Response: ERROR: {str(e)}"

    def send(self, message_text):
        try:
            resp = self.chat.send_message(message_text)
            text = resp.text.strip()
            # If agent requests SQL, run it and feed results back into the chat until agent responds without new "SQL: "
            while text.startswith("SQL:"):
                sql = text[len("SQL:"):].strip()
                sql_response = self._execute_sql_and_format(sql)
                resp = self.chat.send_message(sql_response)
                text = resp.text.strip()
            return text
        except Exception as e:
            return "Sorry, I'm having trouble accessing the knowledge base right now."
