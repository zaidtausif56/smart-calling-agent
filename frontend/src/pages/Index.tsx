import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Phone } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { ThemeToggle } from "@/components/theme-toggle";

const Index = () => {
  const [phoneNumber, setPhoneNumber] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { toast } = useToast();
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

  const handleRequestCall = async () => {
    if (!phoneNumber || phoneNumber.length < 10) {
      toast({
        title: "Invalid phone number",
        description: "Please enter a valid phone number",
        variant: "destructive",
      });
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/make_call`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_number: phoneNumber }),
      });

      if (response.ok) {
        toast({
          title: "Success!",
          description: "You'll receive a call shortly",
        });
        setPhoneNumber("");
      } else {
        throw new Error("Failed to request call");
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to request call. Please try again.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary/10 via-background to-secondary/10">
      <header className="border-b bg-background/80 backdrop-blur-sm">
        <div className="container mx-auto flex h-16 items-center justify-between px-4">
          <h1 className="text-2xl font-bold text-primary">VIT Marketplace</h1>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Button onClick={() => navigate("/login")} variant="outline">
              Login
            </Button>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-16">
        <div className="mx-auto max-w-2xl text-center">
          <div className="mb-8">
            <div className="mb-4 inline-flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
              <Phone className="h-8 w-8 text-primary" />
            </div>
            <h2 className="mb-4 text-4xl font-bold">Order Anything by Phone</h2>
            <p className="text-lg text-muted-foreground">
              Enter your phone number and our AI voice agent will call you to help place your order
            </p>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Request a Call</CardTitle>
              <CardDescription>
                We'll call you within minutes to take your order
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Input
                type="tel"
                placeholder="Enter your phone number"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                className="text-lg"
              />
              <Button
                onClick={handleRequestCall}
                disabled={loading}
                size="lg"
                className="w-full"
              >
                {loading ? "Requesting..." : "Request Call Now"}
              </Button>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
};

export default Index;
