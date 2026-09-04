"""Multiplicadores sectoriales por CLAE2.

Multiplicadores keynesianos-insumo-producto por sector.
Calibrados para Argentina (mercado interno):
  canal de consumo + encadenamiento local con proveedores.

Fuente: estimaciones propias basadas en literatura de economía regional argentina.

Uso:
    from pipeline.multipliers import get_multiplicador
    m = get_multiplicador("29")  # → 2.4 (automotriz)
"""

MULTIPLICADORES: dict[str, float] = {
    "10": 1.8,   # Elaboración de alimentos
    "11": 1.6,   # Elaboración de bebidas
    "12": 1.4,   # Elaboración de tabaco
    "13": 2.1,   # Fabricación de productos textiles
    "14": 2.0,   # Confección de prendas de vestir
    "15": 1.9,   # Curtido y adobo de cueros; calzado
    "16": 1.7,   # Producción de madera; artículos de madera
    "17": 1.8,   # Fabricación de papel y cartón
    "18": 1.6,   # Impresión y reproducción de grabaciones
    "19": 1.5,   # Fabricación de coque y productos de petróleo
    "20": 1.9,   # Fabricación de sustancias y productos químicos
    "21": 1.8,   # Fabricación de productos farmacéuticos
    "22": 1.8,   # Fabricación de productos de caucho y plástico
    "23": 1.7,   # Fabricación de otros productos minerales no metálicos
    "24": 2.2,   # Fabricación de metales comunes (siderurgia, aluminio)
    "25": 2.1,   # Fabricación de productos elaborados de metal
    "26": 2.0,   # Fabricación de equipos de cómputo y electrónica
    "27": 2.3,   # Fabricación de maquinaria y aparatos eléctricos
    "28": 2.2,   # Fabricación de maquinaria y equipo n.c.p.
    "29": 2.4,   # Fabricación de vehículos automotores
    "30": 2.3,   # Fabricación de otro equipo de transporte
    "31": 1.9,   # Fabricación de muebles
    "32": 1.8,   # Otras industrias manufactureras
    "33": 1.7,   # Reparación e instalación de maquinaria
}

MULTIPLICADOR_DEFAULT = 1.8


def get_multiplicador(clae2: str | None) -> float:
    """Retorna el multiplicador para un código CLAE2.

    Si clae2 es None o no está en la tabla, retorna MULTIPLICADOR_DEFAULT (1.8).

    Args:
        clae2: Código CLAE2 como string ('10', '29', etc.).

    Returns:
        Float con el multiplicador sectorial.
    """
    if clae2 is None:
        return MULTIPLICADOR_DEFAULT
    return MULTIPLICADORES.get(str(clae2).zfill(2), MULTIPLICADOR_DEFAULT)
