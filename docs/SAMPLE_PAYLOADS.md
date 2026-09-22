# Hostinger sample (documentation only)

```json
{
  "order_id": "1045",
  "order_date": "April 3, 2026",
  "order_time": "",
  "customer_name": "Customer Name",
  "email": "customer@example.com",
  "phone": "9876543210",
  "payment_method": "Razorpay",
  "total": 1250,
  "address": {"full": "Customer address", "city": "", "pincode": "600001"},
  "products": [
    {"product": "2-in-1 Hair Mask &amp; Conditioner", "variant": "150gm", "quantity": 1, "unit_price": 450},
    {"product": "HERBAL GLOW FACE WASH", "variant": "100ml", "quantity": 1, "unit_price": 250}
  ]
}
```

Source: HOSTINGER. Phone forms 9876543210, 919876543210, +91 98765 43210 and
+91-98765-43210 normalize to +919876543210.
The example order total differs from item totals. Retain both independently;
do not invent shipping/tax/discount breakdowns. Define validation in Phase 2.
