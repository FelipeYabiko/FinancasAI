"""Merchants and people used by the synthetic statement generator.

Bank names are invented. Merchants are generic Brazilian-style descriptors (the kind that
appear on real statements) so categorization evals are realistic.
"""

# (statement descriptor variants, category, typical amount range in cents)
MERCHANTS: list[tuple[list[str], str, tuple[int, int]]] = [
    (["SUPERMERCADO BOM PRECO", "SUPERM BOM PRECO LTDA"], "Mercado", (3500, 48000)),
    (["MERCADINHO DA ESQUINA"], "Mercado", (1200, 9000)),
    (["ATACADAO DO POVO", "ATACADAO POVO SP"], "Mercado", (8000, 65000)),
    (["HORTIFRUTI VERDE VIDA"], "Mercado", (1500, 12000)),
    (["PADARIA PAO DOURADO"], "Mercado", (800, 4500)),
    (["IFOOD *RESTAURANTE SABOR", "IFD*SABOR CASEIRO"], "Delivery", (2500, 11000)),
    (["IFOOD *PIZZARIA FORNO", "IFD*PIZZARIA FORNO"], "Delivery", (4500, 13000)),
    (["RAPPI *BURGER HOUSE"], "Delivery", (3500, 9000)),
    (["RESTAURANTE SABOR DE MINAS"], "Restaurantes", (3000, 18000)),
    (["CANTINA DA NONNA"], "Restaurantes", (6000, 25000)),
    (["CAFE GRAO NOBRE"], "Restaurantes", (900, 4500)),
    (["UBER *TRIP", "UBER *TRIP HELP.UBER.COM"], "Transporte", (900, 6500)),
    (["99APP *CORRIDA", "99 TECNOLOGIA CORRIDA"], "Transporte", (800, 5500)),
    (["POSTO ESTRELA COMBUSTIVEIS", "AUTO POSTO ESTRELA"], "Transporte", (8000, 32000)),
    (["ESTAC CENTRO PARK"], "Transporte", (1000, 3500)),
    (["NETFLIX.COM"], "Assinaturas", (3990, 5590)),
    (["SPOTIFY BRASIL"], "Assinaturas", (2190, 3490)),
    (["AMAZON PRIME BR"], "Assinaturas", (1490, 1990)),
    (["YOUTUBE PREMIUM"], "Assinaturas", (2490, 4190)),
    (["FARMACIA VIDA SAUDE", "DROGARIA VIDA SAUDE"], "Saúde", (1500, 22000)),
    (["LAB CLINICO EXAME"], "Saúde", (8000, 35000)),
    (["ACADEMIA CORPO ATIVO"], "Saúde", (9900, 14900)),
    (["LIVRARIA LER MAIS"], "Educação", (3000, 16000)),
    (["CURSO IDIOMAS FALA BEM"], "Educação", (25000, 45000)),
    (["CINEMA ESTRELA SHOP"], "Lazer", (2500, 9000)),
    (["INGRESSOS SHOW E CIA"], "Lazer", (8000, 40000)),
    (["LOJA MODA URBANA"], "Compras", (6000, 35000)),
    (["MAGAZINE CASA TUDO"], "Compras", (5000, 150000)),
    (["ELETRO CENTER ONLINE"], "Compras", (15000, 400000)),
    (["PET SHOP AMIGO FIEL"], "Pets", (3000, 25000)),
    (["CIA AEREA VOE BEM"], "Viagem", (30000, 180000)),
    (["HOTEL PRAIA AZUL"], "Viagem", (40000, 150000)),
    (["ENERGIA LUZ FORTE SA"], "Contas e serviços", (9000, 42000)),
    (["AGUA E SANEAMENTO CIDADE"], "Contas e serviços", (5000, 18000)),
    (["INTERNET FIBRA RAPIDA"], "Contas e serviços", (9990, 14990)),
    (["TELEFONIA CELULAR MAIS"], "Contas e serviços", (4990, 9990)),
    (["CONDOMINIO RES JARDINS"], "Moradia", (45000, 120000)),
    (["IPTU PREFEITURA PARC"], "Impostos e taxas", (15000, 60000)),
    (["TARIFA PACOTE SERVICOS"], "Impostos e taxas", (1990, 4990)),
]

PEOPLE = [
    "MARIA S OLIVEIRA",
    "JOAO P SANTOS",
    "ANA CAROLINA LIMA",
    "PEDRO H COSTA",
    "LUCIANA M ROCHA",
    "CARLOS E SOUZA",
    "FERNANDA ALVES",
    "RAFAEL G PEREIRA",
]

EMPLOYERS = ["EMPRESA ALFA TECNOLOGIA LTDA", "COMERCIO BETA SA", "INSTITUTO GAMA"]
