# 💧 AspersãoPro

**Projeto profissional de irrigação por aspersão convencional com manejo pelo clima** — em Python, com
interface Streamlit, totalmente em português.

Inspirado no fluxo do *OpenIrri* (El-Naggar, *SoftwareX* 35, 2026, 102912) e estendido com altimetria real
(MDE), integração com Google Earth / Google Maps / Earth Engine, layout automático da rede sobre a área,
hidráulica passo a passo com a cota de cada aspersor, simulação por setor e manejo da irrigação pelo clima.

## Instalação e execução

```bash
cd aspersao_pro
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

O navegador abre em `http://localhost:8501`. Na página **Início**, carregue um projeto-exemplo
(*Cacau irrigado — Oeste da Bahia* ou *Validação — estudo de caso OpenIrri*) ou comece um projeto em branco.

> Recursos online (imagens de satélite, altimetria, NASA POWER, Open-Meteo) exigem internet. Sem conexão o
> programa continua funcionando com normais mensais digitadas, arquivos de estação do INMET/planilhas,
> GeoTIFF, levantamento topográfico ou declividade uniforme.

## Fluxo de projeto (páginas)

| Etapa | O que faz |
|---|---|
| **Área e mapa** | Desenho do polígono sobre **Google Satélite/Híbrido/Terreno** (imagens do Google Earth) ou Esri; busca de endereço; importação **KML/KMZ do Google Earth Pro** e GeoJSON; captação (bomba) e rota da adutora; área em SIRGAS 2000/UTM. |
| **Altimetria** | MDE por Open-Meteo (Copernicus GLO-90), OpenTopoData (SRTM/ASTER 30 m), Open-Elevation, **Google Maps Elevation API** (chave), **Google Earth Engine** (SRTM, NASADEM, Copernicus 30 m), GeoTIFF próprio ou pontos de levantamento GNSS/estação total. Curvas de nível sobre a imagem de satélite, relevo 3D, mapa de declividade, plano médio. |
| **Clima e ETo** | Série diária NASA POWER ou Open-Meteo/ERA5, CSV horário de **estação automática do INMET**, planilha diária, normais mensais ou ETo mensal. ETo **FAO-56 Penman-Monteith** própria (com procedimentos para dados ausentes e Hargreaves). |
| **Cultura e necessidade hídrica** | Kc FAO-56 (30 culturas, inclusive cacau, café, citros, cana, grãos, hortaliças) com **ajuste climático (Eq. 62)**; balanço climático mensal; ETc de projeto por Kc×ETo máxima, maior ETc mensal do ciclo ou **análise de frequência** (quantil dos máximos anuais da média móvel do turno de rega); lâminas LL e LB. |
| **Aspersor e uniformidade** | Catálogo de referência + importação do catálogo do fabricante (CSV); q = k·Pˣ; **simulação por superposição** do perfil radial (CUC de Christiansen, CUD, CUH) com **distorção pelo vento** e perfil medido opcional; perdas por evaporação e deriva (**Trimmer, 1987**); eficiência de distribuição (Keller & Bliesner); **otimizador** de aspersor × pressão × espaçamento. |
| **Operação e setorização** | Tempo de aplicação, posições por dia, número de setores (restrição N ≤ ns·I), vazão do sistema × fonte, cronograma e Gantt (início padrão 21h30 — tarifa noturna). |
| **Layout da rede** | Geração automática em pente: adutora → principal → derivações → laterais, **laterais em nível** pelo MDE, comprimento máximo de lateral calculado, setores contíguos por derivação. Exporta **KMZ para o Google Earth**, **DXF** (CAD) e GeoJSON. |
| **Hidráulica** | Hazen-Williams ou Darcy-Weisbach; laterais passo a passo com a cota de cada aspersor (verificação pelo fator F de Christiansen); variação ≤ 20 %; derivação/principal/adutora por velocidade ou **diâmetro econômico**; variação entre laterais do setor com aumento guloso de diâmetros e **reguladores de pressão**; classes PN; ventosas e descargas pelo perfil; **golpe de aríete**; **simulação do setor** com vazões dependentes da pressão. |
| **Bomba e energia** | Altura manométrica (cascata), NPSH disponível × requerido, potências, motor comercial com folga, rotação automática, curva genérica ou do fabricante, ponto de operação e requisitos de todos os setores, inversor de frequência, energia anual com **desconto da tarifa noturna para irrigantes** ou diesel. |
| **Orçamento** | Lista de materiais a partir da rede dimensionada; preços e catálogo de tubos editáveis; investimento, custo anual (capital, manutenção, energia, água) e custo do m³. |
| **Manejo pelo clima** | **Boletim de irrigação** com observações recentes + previsão de 16 dias (Open-Meteo), adiamento por chuva prevista, tempo de cada setor; tanque Classe A (Kp de Snyder); estação local; **simulação plurianual** da operação (volume, horas, atendimento da demanda). |
| **Relatórios** | Memorial descritivo e de cálculo em **PDF**, planilha **Excel**, KMZ, DXF e o projeto completo em JSON (reprodutível). |

## Manejo pelo clima (premissa de projeto)

O sistema é dimensionado para manejo **pelo clima, e não pelo solo**:

- a lâmina de cada irrigação repõe a ETc acumulada desde a irrigação anterior, descontada a chuva efetiva:
  `S_t = máx(S_t−1 + ETc_t − Pe_t − I_t ; −Cmáx)`;
- o **turno de rega** é uma decisão operacional (não é derivado da capacidade de água disponível do solo);
- projeto: `LL = ETc_proj × TR`, `LB = LL / Ea`, `Ti = LB / Ia`;
- o solo entra apenas como **limite de intensidade de aplicação** (VIB), para evitar escoamento.

## Validação

`pytest` executa 59 testes, entre eles:

- FAO-56: Exemplos 2, 8, 14, **17 (ETo mensal, Bangkok = 5,72 mm/d)** e **18 (ETo diária, Bruxelas = 3,9 mm/d)**;
- fator F exato × fórmula de Christiansen; passo a passo × método analítico (diferença < 1 %);
- balanço de massa da superposição (lâmina média simulada = q / (Sa·Sl));
- **reprodução do estudo de caso do OpenIrri**: ETc 11,65 mm/d, Ia 3,28 mm/h, 672 aspersores, 2 setores,
  vazão ≤ 200 m³/h, variação de pressão na lateral ≤ 20 %;
- rede: diâmetros telescópicos nas derivações, velocidades, simulação do setor × dimensionamento.

```bash
cd aspersao_pro && python -m pytest -q
```

## Uso como biblioteca

```python
from aspersao.projeto import exemplo_cacau_bahia
from aspersao.pipeline import executar_tudo
from aspersao import relatorios

p = exemplo_cacau_bahia()
r = executar_tudo(p)
print(r["agronomico"]["projeto"], r["bomba"]["Hman"])
open("memorial.pdf", "wb").write(relatorios.gerar_pdf(p, r))
```

## Avisos importantes

- O **catálogo de aspersores e os preços** são de referência (equação do orifício; massa de material). Para projeto
  executivo, importe o catálogo do fabricante e atualize as cotações.
- A **curva genérica da bomba** e o NPSHr estimado (Thoma/Stepanoff) servem para pré-seleção; confirme com a curva
  do fabricante (página Bomba → "Do fabricante").
- Os **projetos-exemplo** usam clima e relevo ilustrativos; substitua por dados reais.
- As camadas do Google são carregadas diretamente dos servidores de mosaicos; o uso está sujeito aos termos do Google.
  A chave da Google Elevation API fica apenas na sessão (não é gravada no JSON do projeto).

## Estrutura

```
aspersao_pro/
├── app.py                  # aplicação Streamlit
├── aspersao/               # motor de cálculo (independente da interface)
│   ├── clima/              # penman.py (FAO-56), fontes.py (NASA/Open-Meteo/INMET), estatistica.py
│   ├── cultura.py  necessidade.py  aspersores.py  uniformidade.py
│   ├── hidraulica.py  tubos.py  rede.py  layout.py  operacao.py  bomba.py
│   ├── altimetria.py  geo.py  exportar.py  custos.py  manejo.py
│   ├── pipeline.py         # encadeamento reativo com cache por etapa
│   ├── projeto.py          # estrutura do projeto, exemplos, JSON
│   └── relatorios.py       # PDF e Excel
├── interface/              # páginas, gráficos (Plotly) e mapas (folium)
└── tests/                  # validação (pytest)
```

## Referências principais

Allen et al. (1998) FAO-56 · Christiansen (1942) · Keller & Bliesner (1990) · Bernardo et al. (2019) Manual de
Irrigação · Trimmer (1987) · Snyder (1992) · Swamee & Jain (1976) · El-Naggar (2026) OpenIrri, SoftwareX 35:102912 ·
ANEEL REN 1.000/2021.
