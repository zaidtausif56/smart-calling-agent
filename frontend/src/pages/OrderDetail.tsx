import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import { ArrowLeft, Trash2 } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface OrderDetail {
  id: string;  // UUID string
  phone_number: string;
  product_name: string;
  quantity: number;
  total_price: number;
  delivery_address?: string;
  order_status: string;
  created_at: string;
}

const OrderDetail = () => {
  const { orderId } = useParams();
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [orderNumber, setOrderNumber] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [showCancelDialog, setShowCancelDialog] = useState(false);
  const navigate = useNavigate();
  const { toast } = useToast();
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:5000";
  
  useEffect(() => {
    const authToken = localStorage.getItem("authToken");
    if (!authToken) {
      navigate("/login");
      return;
    }

    fetchOrderDetail(authToken);
  }, [orderId, navigate]);

  const fetchOrderDetail = async (authToken: string) => {
    try {
      // Fetch all orders to determine the sequential order number
      const allOrdersResponse = await fetch(`${API_BASE_URL}/api/orders`, {
        headers: {
          Authorization: `Bearer ${authToken}`,
          "ngrok-skip-browser-warning": "true",
        },
      });

      const response = await fetch(`${API_BASE_URL}/api/orders/${orderId}`, {
        headers: {
          Authorization: `Bearer ${authToken}`,
          "ngrok-skip-browser-warning": "true",
        },
      });

      if (response.ok && allOrdersResponse.ok) {
        const data = await response.json();
        const allOrdersData = await allOrdersResponse.json();
        setOrder(data.order);
        
        // Calculate sequential order number (most recent = 1)
        const allOrders = allOrdersData.orders || [];
        const orderIndex = allOrders.findIndex((o: OrderDetail) => o.id === orderId);
        setOrderNumber(allOrders.length - orderIndex);
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
        throw new Error("Failed to fetch order details");
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to load order details",
        variant: "destructive",
      });
      navigate("/orders");
    } finally {
      setLoading(false);
    }
  };

  const handleCancelOrder = async () => {
    const authToken = localStorage.getItem("authToken");
    try {
      const response = await fetch(`${API_BASE_URL}/api/orders/${orderId}`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${authToken}`,
          "ngrok-skip-browser-warning": "true",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ status: "cancelled" }),
      });

      if (response.ok) {
        toast({
          title: "Order cancelled",
          description: "Your order has been cancelled successfully",
        });
        setShowCancelDialog(false);
        // Refresh the order to show updated status
        const updatedOrder = { ...order!, order_status: "cancelled" };
        setOrder(updatedOrder);
      } else {
        throw new Error("Failed to cancel order");
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to cancel order",
        variant: "destructive",
      });
    }
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

  const canCancel = order?.order_status.toLowerCase() === "confirmed";

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center">Loading...</div>;
  }

  if (!order) {
    return <div className="flex min-h-screen items-center justify-center">Order not found</div>;
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto flex h-16 items-center justify-between px-4">
          <Button variant="ghost" size="sm" onClick={() => navigate("/orders")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Orders
          </Button>
          <ThemeToggle />
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        <div className="mx-auto max-w-3xl space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between">
                <div>
                  <CardTitle>Order #{order.id}</CardTitle>
                  <CardDescription>
                    Placed on {new Date(order.created_at).toLocaleDateString('en-US', {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </CardDescription>
                </div>
                <Badge className={getStatusColor(order.order_status)}>{order.order_status}</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              <div>
                <h3 className="mb-4 font-semibold">Order Details</h3>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <div>
                      <p className="font-medium">{order.product_name}</p>
                      <p className="text-sm text-muted-foreground">Quantity: {order.quantity}</p>
                    </div>
                    <p className="font-semibold">₹{order.total_price.toFixed(2)}</p>
                  </div>
                </div>
              </div>

              <Separator />

              <div className="flex justify-between text-lg font-bold">
                <span>Total</span>
                <span>₹{order.total_price.toFixed(2)}</span>
              </div>

              <Separator />

              <div>
                <h3 className="mb-2 font-semibold">Contact Information</h3>
                <p className="text-muted-foreground">{order.phone_number}</p>
              </div>

              {order.delivery_address && (
                <>
                  <Separator />
                  <div>
                    <h3 className="mb-2 font-semibold">Delivery Address</h3>
                    <p className="text-muted-foreground whitespace-pre-line">{order.delivery_address}</p>
                  </div>
                </>
              )}

              {canCancel && (
                <>
                  <Separator />
                  <Button
                    variant="destructive"
                    className="w-full"
                    onClick={() => setShowCancelDialog(true)}
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    Cancel Order
                  </Button>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </main>

      <AlertDialog open={showCancelDialog} onOpenChange={setShowCancelDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will permanently cancel your order.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep Order</AlertDialogCancel>
            <AlertDialogAction onClick={handleCancelOrder} className="bg-destructive text-destructive-foreground">
              Cancel Order
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};

export default OrderDetail;
