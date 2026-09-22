-- Only the eight explicitly supplied mappings. Do not infer missing historical aliases.
-- normalized_alias stores the decoded, trimmed, lowercase product name only.
-- Resolver must separately normalize and compare alias_variant (NULL/blank => NULL).
INSERT INTO product_aliases
(product_id, variant_id, source_system, alias_name, alias_variant, normalized_alias)
SELECT p.id, pv.id, 'HOSTINGER', a.alias_name, a.alias_variant, a.normalized_alias
FROM (VALUES
('Herbal Hair Color - Natural Black', 'Natural Black', 'Herbal Hair Color', 'Natural Black 75g', 'herbal hair color - natural black'),
('HERBAL GLOW FACE WASH', '100ml', 'Herbal Glow Face Wash', '100 ml', 'herbal glow face wash'),
('Thaazhai Herbal Conditioning Shampoo', '100', 'Thaazhai Herbal Conditioning Shampoo', '100 ml', 'thaazhai herbal conditioning shampoo'),
('Thaazhai Herbal Conditioning Shampoo', '100 ml', 'Thaazhai Herbal Conditioning Shampoo', '100 ml', 'thaazhai herbal conditioning shampoo'),
('Thaazhai Herbal Conditioning Shampoo', '200 ml', 'Thaazhai Herbal Conditioning Shampoo', '200 ml', 'thaazhai herbal conditioning shampoo'),
('Rose &amp; Vetiver Body Wash', '100ml', 'Rose & Vetiver Body Wash', '100 ml', 'rose & vetiver body wash'),
('2-in-1 Hair Mask &amp; Conditioner', '150gm', '2-in-1 Hair Mask & Conditioner', '150 gm', '2-in-1 hair mask & conditioner'),
('Herbal Hair Colour + Aloe Vera Combo', NULL, 'Thaazhai Aloevera Gel and Hair colour', 'Kit', 'herbal hair colour + aloe vera combo')
) AS a(alias_name, alias_variant, product_name, variant_name, normalized_alias)
JOIN products p ON p.canonical_name = a.product_name
JOIN product_variants pv ON pv.product_id = p.id AND pv.variant_name = a.variant_name
WHERE NOT EXISTS (
 SELECT 1 FROM product_aliases existing
 WHERE existing.source_system = 'HOSTINGER'
 AND existing.alias_name = a.alias_name
 AND existing.alias_variant IS NOT DISTINCT FROM a.alias_variant
);
