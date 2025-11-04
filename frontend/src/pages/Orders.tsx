import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { LogOut, Package, MapPin, Phone } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";

interface Order {
  id: string;  // UUID string
  phone_number: string;
  product_name: string;
  quantity: number;
  total_price: number;
  delivery_address?: string;
  order_status: string;
  created_at: string;
}

const Orders = () => {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [phoneNumber, setPhoneNumber] = useState("");
  const navigate = useNavigate();
  const { toast } = useToast();
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:5000";


  useEffect(() => {
    const authToken = localStorage.getItem("authToken");
    const storedPhone = localStorage.getItem("phoneNumber");
    if (!authToken || !storedPhone) {
      navigate("/login");
      return;
    }
    setPhoneNumber(storedPhone);
    fetchOrders(authToken);
  }, [navigate]);

  const fetchOrders = async (authToken: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/orders`, {
        headers: {
          Authorization: `Bearer ${authToken}`,
          "ngrok-skip-browser-warning": "true",
        },
      });

      if (response.ok) {
        const data = await response.json();
        setOrders(data.orders || []);
      } else if (response.status === 401) {
        toast({
          title: "Session expired",
          description: "Please login again",
          variant: "destructive",
        });
        localStorage.removeItem("authToken");
        localStorage.removeItem("phoneNumber");
        navigate("/login");
      } else {
        throw new Error("Failed to fetch orders");
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to load orders",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("authToken");
    localStorage.removeItem("phoneNumber");
    navigate("/");
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case "delivered":
        return "bg-green-500";
      case "shipped":
        return "bg-blue-500";
      case "confirmed":
        return "bg-purple-500";
      case "cancelled":
        return "bg-red-500";
      default:
        return "bg-yellow-500";
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto flex h-16 items-center justify-between px-4">
          <div>
            <h1 className="text-2xl font-bold text-primary">My Orders</h1>
            <p className="text-xs text-muted-foreground">{phoneNumber}</p>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={() => navigate("/")} variant="default" size="sm">
              <Phone className="mr-2 h-4 w-4" />
              Place Order
            </Button>
            <ThemeToggle />
            <Button onClick={handleLogout} variant="outline" size="sm">
              <LogOut className="mr-2 h-4 w-4" />
              Logout
            </Button>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        {loading ? (
          <div className="text-center">Loading orders...</div>
        ) : orders.length === 0 ? (
          <Card className="mx-auto max-w-md">
            <CardContent className="flex flex-col items-center py-8">
              <Package className="mb-4 h-16 w-16 text-muted-foreground" />
              <h2 className="mb-2 text-xl font-semibold">No orders yet</h2>
              <p className="mb-4 text-muted-foreground">
                Request a call to place your first order
              </p>
              <Button onClick={() => navigate("/")}>Go to Home</Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {orders.map((order, index) => (
              <Card
                key={order.id}
                className="cursor-pointer transition-shadow hover:shadow-lg"
                onClick={() => navigate(`/orders/${order.id}`)}
              >
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <CardTitle className="text-lg">Order #{orders.length - index}</CardTitle>
                    <Badge className={getStatusColor(order.order_status)}>
                      {order.order_status}
                    </Badge>
                  </div>
                  <CardDescription>
                    {new Date(order.created_at).toLocaleDateString('en-US', {
                      year: 'numeric',
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <p className="text-sm font-medium">{order.product_name}</p>
                    <p className="text-sm text-muted-foreground">
                      Quantity: {order.quantity}
                    </p>
                    {order.delivery_address && (
                      <div className="flex items-start gap-1 text-sm text-muted-foreground">
                        <MapPin className="mt-0.5 h-4 w-4 flex-shrink-0" />
                        <p className="line-clamp-2">
                          {order.delivery_address}
                        </p>
                      </div>
                    )}
                    <p className="text-lg font-semibold">
                      ₹{order.total_price.toFixed(2)}
                    </p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  );
};

export default Orders;
