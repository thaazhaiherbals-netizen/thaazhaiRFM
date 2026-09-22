CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_name VARCHAR(255),
    normalized_phone VARCHAR(30),
    email VARCHAR(255),
    first_order_date DATE,
    last_order_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_phone
ON customers(normalized_phone) WHERE normalized_phone IS NOT NULL;
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingestion_id UUID NOT NULL REFERENCES raw_order_ingestion(id),
    customer_id UUID REFERENCES customers(id),
    source_system VARCHAR(30) NOT NULL,
    source_record_id VARCHAR(150) NOT NULL,
    order_date DATE NOT NULL,
    payment_method VARCHAR(100),
    order_value NUMERIC(12,2) NOT NULL,
    address JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(source_system, source_record_id),
    UNIQUE(ingestion_id)
);
CREATE TABLE IF NOT EXISTS order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id),
    variant_id UUID REFERENCES product_variants(id),
    raw_product_name VARCHAR(255),
    raw_variant_name VARCHAR(150),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12,2),
    line_total NUMERIC(12,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
