-- scripts/seed_test_events.sql
-- Datos de prueba: eventos de cierre para desarrollo local
-- Ejecutar en Supabase SQL Editor después de aplicar 001_initial.sql

INSERT INTO factory_events
  (empresa, localidad_raw, localidad_norm, codgeo_prov, codgeo_depto,
   lat, lng, empleados_afectados, clae2, fecha_evento, tipo_evento,
   fuente_url, fuente_nombre, ingested_from)
VALUES
  -- Gran Buenos Aires (codgeo 06270 = San Martín, prov. Buenos Aires)
  ('Textil San Martín S.A.', 'San Martín', 'San Martín', '06', '06270',
   -34.5750, -58.5350, 320, '13', '2023-03-15', 'cierre',
   'https://example.com/noticia1', 'Infobae', 'seed_test'),

  ('Metalúrgica del Norte', 'Gral. San Martín', 'San Martín', '06', '06270',
   -34.5780, -58.5280, 85, '24', '2022-08-01', 'suspension',
   'https://example.com/noticia2', 'Télam', 'seed_test'),

  -- Córdoba (02007 = Capital, prov. Córdoba)
  ('AutoParts Córdoba S.A.', 'Córdoba Capital', 'Córdoba', '14', '14014',
   -31.4167, -64.1833, 540, '29', '2024-01-20', 'cierre',
   'https://example.com/noticia3', 'La Voz del Interior', 'seed_test'),

  -- Pueblo pequeño de alta dependencia (50007 = Capital, prov. Neuquén)
  ('Cerámica Neuquén', 'Neuquén Capital', 'Neuquén', '58', '58007',
   -38.9516, -68.0591, 95, '23', '2023-11-05', 'cierre',
   'https://example.com/noticia4', 'La Mañana de Neuquén', 'seed_test'),

  -- Santa Fe (82028 = Rosario, prov. Santa Fe)
  ('Frigorífico Rosario S.A.', 'Rosario', 'Rosario', '82', '82028',
   -32.9468, -60.6393, 210, '10', '2022-05-12', 'reduccion',
   'https://example.com/noticia5', 'La Capital', 'seed_test'),

  -- Tucumán (90021 = Capital, prov. Tucumán)
  ('Azucarera del Norte', 'San Miguel de Tucumán', 'Tucumán', '90', '90021',
   -26.8241, -65.2226, 410, '10', '2023-07-30', 'cierre',
   'https://example.com/noticia6', 'La Gaceta', 'seed_test');
