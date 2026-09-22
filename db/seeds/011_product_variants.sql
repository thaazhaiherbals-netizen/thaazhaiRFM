INSERT INTO product_variants (product_id, variant_name, sku, zoho_item_name, variant_type)
SELECT p.id, v.variant_name, v.sku, v.zoho_item_name, v.variant_type
FROM (VALUES
('Herbal Hair Color', 'Natural Black 75g', 'TH-HAIR-COL-075G', 'Herbal Hair Colour Black', 'STANDARD'),
('Thaazhai Rosemary Hydrosol', '100 ml', NULL, NULL, 'STANDARD'),
('Thaazhai Herbal Conditioning Shampoo', '20 ml', 'TH-HAIR-SHAM-020M', NULL, 'SAMPLE'),
('Thaazhai Herbal Conditioning Shampoo', '100 ml', 'TH-HAIR-SHAM-100M', NULL, 'STANDARD'),
('Thaazhai Herbal Conditioning Shampoo', '200 ml', 'TH-HAIR-SHAM-200M', NULL, 'STANDARD'),
('Thaazhai Aloe Vera Premium Natural Moisturizing Gel', '200 gms', 'TH-FACE-GEL-200G', NULL, 'STANDARD'),
('Thaazhai Complete Hair Care Combo 1', 'Kit', 'TH-COMBO-HAIR-C01', NULL, 'STANDARD'),
('Thaazhai Rose Hydrosol', '100 ml', 'TH-FACE-HYD-ROSE', NULL, 'STANDARD'),
('Hair Growth Serum', '50 ml', NULL, NULL, 'STANDARD'),
('Herbal Glow Face Wash', '100 ml', 'TH-FACE-WASH-100M', NULL, 'STANDARD'),
('Thaazhai Complete Hair Care Combo 2', 'Kit', 'TH-COMBO-HAIR-C02', NULL, 'STANDARD'),
('Thaazhai Aloevera Gel and Hair colour', 'Kit', NULL, NULL, 'STANDARD'),
('Manjistha & Licorice Radiance Soap', '100 gms', 'TH-BODY-SOAP-MAN', NULL, 'STANDARD'),
('Thaazhai Hair Strengthening Duo', 'Kit', 'TH-COMBO-SHAM200-ROSM', NULL, 'STANDARD'),
('A2 Ghee Lip Balm', 'Rose - Tinted', 'TH-LIP-BALM-ROSE', NULL, 'STANDARD'),
('A2 Ghee Lip Balm', 'Lemon - Plain', NULL, NULL, 'STANDARD'),
('Glow Booster Skin Serum', '30 ml', 'TH-FACE-SER-030M', NULL, 'STANDARD'),
('Rose & Vetiver Body Wash', '100 ml', 'TH-BODY-WASH-100M', NULL, 'STANDARD'),
('Elladi Ayurvedic Radiance Day Cream', '50 gm', 'TH-FACE-DCRM-050G', NULL, 'STANDARD'),
('Rose Hydrosol & Aloe Vera Gel Combo', 'Kit', 'TH-COMBO-ROSE-GEL', NULL, 'STANDARD'),
('Anti-Frizz Gold Hair Serum', '30 ml', 'TH-HAIR-SER-030M', NULL, 'STANDARD'),
('ABC Radiance Soap – Apple • Beetroot • Carrot', '100 gms', 'TH-BODY-SOAP-ABC', NULL, 'STANDARD'),
('Thaazhai Hair Serum', '30 ml', NULL, NULL, 'STANDARD'),
('Tejas Night Cream', '50 gm', NULL, NULL, 'STANDARD'),
('2-in-1 Hair Mask & Conditioner', '150 gm', 'TH-HAIR-MASK-150G', NULL, 'STANDARD')
) AS v(product_name, variant_name, sku, zoho_item_name, variant_type)
JOIN products p ON p.canonical_name = v.product_name
ON CONFLICT (product_id, variant_name) DO NOTHING;
