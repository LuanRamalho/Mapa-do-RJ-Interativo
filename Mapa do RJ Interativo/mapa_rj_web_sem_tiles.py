# mapa_rj_web_sem_tiles.py
# ============================================================
# MAPA INTERATIVO DOS 92 MUNICÍPIOS DO RIO DE JANEIRO
#
# IMPORTANTE:
# Esta versão NÃO utiliza OpenStreetMap nem qualquer servidor
# de "tiles". Portanto, não aparecerá o erro 403 "Access blocked".
#
# O programa consulta diretamente as APIs públicas do IBGE:
#   1. API de Localidades -> 92 municípios e códigos IBGE
#   2. API de Malhas -> limites geográficos dos municípios
#   3. API SIDRA -> população estimada de 2026
#
# Depois, o Python incorpora os dados no próprio HTML.
# O navegador abre UM ÚNICO ARQUIVO HTML local.
#
# Não precisa de:
#   CSV
#   XLSX
#   ODS
#   Shapefile
#   GeoPandas
#   Folium
#   Leaflet
#
# A única dependência Python é:
#   requests
#
# Com o cursor sobre um município:
#   - o município fica amarelo;
#   - aparece o nome;
#   - aparece a população estimada.
#
# O mapa pode ser arrastado e ampliado/reduzido com a roda
# do mouse.
# ============================================================

from __future__ import annotations

import json
import sys
import webbrowser
from html import escape
from pathlib import Path

import requests


# ------------------------------------------------------------
# CONFIGURAÇÕES
# ------------------------------------------------------------

UF_RJ = "33"
TOTAL_MUNICIPIOS = 92
ANO_POPULACAO = 2026

ARQUIVO_HTML = (
    Path(__file__).resolve().parent
    / "mapa_rio_de_janeiro_92_municipios.html"
)

URL_MUNICIPIOS = (
    "https://servicodados.ibge.gov.br/api/v1/"
    "localidades/estados/33/municipios"
)

URL_MALHA_ESTADO = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/"
    "estados/33"
)

URL_POPULACAO = (
    "https://apisidra.ibge.gov.br/values/"
    "t/6579/"
    "n6/in%20n3%2033/"
    f"p/{ANO_POPULACAO}/"
    "v/9324"
    "?formato=json"
)

CABECALHOS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/153 Safari/537.36"
    )
}


# ------------------------------------------------------------
# INTERNET
# ------------------------------------------------------------

def obter_json(url: str, descricao: str):
    """Consulta uma API pública e devolve o JSON."""
    print(f"\nConsultando {descricao}...")
    print(url)

    try:
        resposta = requests.get(
            url,
            headers=CABECALHOS,
            timeout=120,
        )
        resposta.raise_for_status()
    except requests.RequestException as erro:
        raise RuntimeError(
            f"Não foi possível acessar a fonte:\n{url}\n\n"
            f"Erro: {erro}"
        ) from erro

    try:
        return resposta.json()
    except ValueError as erro:
        raise RuntimeError(
            "A fonte respondeu, mas não devolveu JSON válido."
        ) from erro


# ------------------------------------------------------------
# MUNICÍPIOS
# ------------------------------------------------------------

def obter_municipios():
    """Obtém os 92 municípios diretamente do IBGE."""
    dados = obter_json(
        URL_MUNICIPIOS,
        "a lista de municípios do Estado do Rio de Janeiro",
    )

    municipios = {}

    for item in dados:
        codigo = str(item.get("id", "")).strip()
        nome = str(item.get("nome", "")).strip()

        if len(codigo) == 7 and nome:
            municipios[codigo] = nome

    if len(municipios) != TOTAL_MUNICIPIOS:
        raise RuntimeError(
            f"A API retornou {len(municipios)} municípios do RJ. "
            f"O esperado é {TOTAL_MUNICIPIOS}."
        )

    return municipios


# ------------------------------------------------------------
# MALHA GEOGRÁFICA
# ------------------------------------------------------------

def obter_malha(municipios):
    """
    Obtém a malha municipal diretamente da API do IBGE.

    A primeira tentativa pede os 92 municípios em uma só chamada.
    Se a API não devolver exatamente 92 áreas, o programa tenta
    obter cada município individualmente.
    """
    url = (
        URL_MALHA_ESTADO
        + "?intrarregiao=municipios"
        "&formato=application/vnd.geo+json"
        "&qualidade=intermediaria"
    )

    print(
        "\nObtendo a malha geográfica dos 92 municípios..."
    )

    try:
        dados = obter_json(
            url,
            "a malha municipal do Estado do Rio de Janeiro",
        )

        if (
            isinstance(dados, dict)
            and dados.get("type") == "FeatureCollection"
            and len(dados.get("features", []))
            == TOTAL_MUNICIPIOS
        ):
            return dados

    except RuntimeError:
        pass

    print(
        "\nA API não retornou os 92 municípios em uma única "
        "resposta. Vou obter as geometrias individualmente."
    )

    features = []

    for indice, codigo in enumerate(
        sorted(municipios),
        start=1,
    ):
        url_municipio = (
            "https://servicodados.ibge.gov.br/api/v3/"
            f"malhas/municipios/{codigo}"
            "?formato=application/vnd.geo+json"
            "&qualidade=intermediaria"
        )

        dados = obter_json(
            url_municipio,
            (
                f"a malha de {municipios[codigo]} "
                f"({indice}/{TOTAL_MUNICIPIOS})"
            ),
        )

        if not isinstance(dados, dict):
            continue

        if dados.get("type") == "Feature":
            feature = dados

        elif (
            dados.get("type") == "FeatureCollection"
            and dados.get("features")
        ):
            feature = dados["features"][0]

        else:
            continue

        feature.setdefault("properties", {})
        feature["properties"]["codigo_ibge"] = codigo

        features.append(feature)

    if len(features) != TOTAL_MUNICIPIOS:
        raise RuntimeError(
            f"Somente {len(features)} geometrias foram obtidas. "
            f"O esperado é {TOTAL_MUNICIPIOS}."
        )

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def codigo_da_feature(feature) -> str:
    """Localiza o código IBGE dentro de uma Feature GeoJSON."""
    propriedades = feature.get(
        "properties",
        {},
    )

    candidatos = [
        propriedades.get("codigo_ibge"),
        propriedades.get("codarea"),
        propriedades.get("CD_MUN"),
        propriedades.get("CD_GEOCMU"),
        propriedades.get("id"),
        feature.get("id"),
    ]

    for valor in candidatos:
        if valor is None:
            continue

        texto = str(valor).strip()

        if texto.endswith(".0"):
            texto = texto[:-2]

        numeros = "".join(
            caractere
            for caractere in texto
            if caractere.isdigit()
        )

        if len(numeros) == 7:
            return numeros

    return ""


# ------------------------------------------------------------
# POPULAÇÃO
# ------------------------------------------------------------

def obter_populacao():
    """Obtém população estimada 2026 diretamente do SIDRA/IBGE."""
    dados = obter_json(
        URL_POPULACAO,
        (
            f"a população estimada dos municípios do RJ "
            f"para {ANO_POPULACAO}"
        ),
    )

    populacao = {}

    for item in dados:
        if not isinstance(item, dict):
            continue

        codigo = str(
            item.get("D1C", "")
        ).strip()

        valor = item.get("V")

        if len(codigo) != 7:
            continue

        try:
            numero = int(
                float(
                    str(valor)
                    .replace(",", ".")
                )
            )
        except (
            ValueError,
            TypeError,
        ):
            continue

        populacao[codigo] = numero

    if len(populacao) != TOTAL_MUNICIPIOS:
        raise RuntimeError(
            f"O SIDRA retornou {len(populacao)} populações "
            f"do RJ. O esperado é {TOTAL_MUNICIPIOS}."
        )

    return populacao


# ------------------------------------------------------------
# GEOJSON FINAL
# ------------------------------------------------------------

def montar_geojson(
    municipios,
    geojson,
    populacao,
):
    """Adiciona nome e população às 92 geometrias."""
    features_finais = []
    encontrados = set()

    for feature in geojson["features"]:
        codigo = codigo_da_feature(feature)

        if codigo not in municipios:
            continue

        if codigo not in populacao:
            raise RuntimeError(
                f"A população de {municipios[codigo]} "
                f"({codigo}) não foi encontrada no SIDRA."
            )

        nova = json.loads(
            json.dumps(feature)
        )

        nova.setdefault(
            "properties",
            {},
        )

        nova["properties"].update(
            {
                "codigo_ibge": codigo,
                "municipio": municipios[codigo],
                "populacao": populacao[codigo],
            }
        )

        features_finais.append(nova)
        encontrados.add(codigo)

    if len(features_finais) != TOTAL_MUNICIPIOS:
        faltantes = sorted(
            set(municipios) - encontrados
        )

        raise RuntimeError(
            f"A montagem do mapa produziu "
            f"{len(features_finais)} municípios em vez de 92.\n\n"
            "Faltantes:\n"
            + "\n".join(
                f" - {municipios[codigo]}"
                for codigo in faltantes
            )
        )

    return {
        "type": "FeatureCollection",
        "features": features_finais,
    }


# ------------------------------------------------------------
# PROJEÇÃO PARA SVG
# ------------------------------------------------------------

def iter_coordinates(geometria):
    """Percorre recursivamente coordenadas de uma geometria."""
    tipo = geometria.get("type")
    coordenadas = geometria.get("coordinates")

    if tipo == "Point":
        yield coordenadas

    elif tipo == "MultiPoint":
        for ponto in coordenadas:
            yield ponto

    elif tipo in (
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
    ):
        if tipo == "LineString":
            for ponto in coordenadas:
                yield ponto
            return

        if tipo == "MultiLineString":
            for linha in coordenadas:
                for ponto in linha:
                    yield ponto
            return

        if tipo == "Polygon":
            for anel in coordenadas:
                for ponto in anel:
                    yield ponto
            return

        if tipo == "MultiPolygon":
            for poligono in coordenadas:
                for anel in poligono:
                    for ponto in anel:
                        yield ponto


def calcular_limites(geojson):
    """Calcula o bounding box das 92 geometrias."""
    longitudes = []
    latitudes = []

    for feature in geojson["features"]:
        geometria = feature["geometry"]

        for ponto in iter_coordinates(geometria):
            if len(ponto) >= 2:
                longitudes.append(float(ponto[0]))
                latitudes.append(float(ponto[1]))

    if not longitudes:
        raise RuntimeError(
            "A malha não possui coordenadas."
        )

    margem = 0.15

    return (
        min(longitudes) - margem,
        min(latitudes) - margem,
        max(longitudes) + margem,
        max(latitudes) + margem,
    )


def projetar_ponto(
    longitude,
    latitude,
    limites,
    largura,
    altura,
):
    """
    Converte longitude/latitude para coordenadas SVG.
    Usa uma projeção equiretangular adequada para esta
    visualização regional.
    """
    min_lon, min_lat, max_lon, max_lat = limites

    x = (
        (longitude - min_lon)
        / (max_lon - min_lon)
        * largura
    )

    y = (
        (max_lat - latitude)
        / (max_lat - min_lat)
        * altura
    )

    return x, y


def anel_para_svg(
    anel,
    limites,
    largura,
    altura,
):
    """Converte um anel GeoJSON em comandos SVG."""
    if not anel:
        return ""

    partes = []

    for indice, ponto in enumerate(anel):
        x, y = projetar_ponto(
            float(ponto[0]),
            float(ponto[1]),
            limites,
            largura,
            altura,
        )

        comando = "M" if indice == 0 else "L"

        partes.append(
            f"{comando}{x:.2f},{y:.2f}"
        )

    partes.append("Z")

    return " ".join(partes)


def geometria_para_svg(
    geometria,
    limites,
    largura,
    altura,
):
    """Converte Polygon/MultiPolygon em um único path SVG."""
    tipo = geometria.get("type")
    coordenadas = geometria.get("coordinates")

    partes = []

    if tipo == "Polygon":
        for anel in coordenadas:
            partes.append(
                anel_para_svg(
                    anel,
                    limites,
                    largura,
                    altura,
                )
            )

    elif tipo == "MultiPolygon":
        for poligono in coordenadas:
            for anel in poligono:
                partes.append(
                    anel_para_svg(
                        anel,
                        limites,
                        largura,
                        altura,
                    )
                )

    else:
        raise RuntimeError(
            f"Tipo de geometria não suportado: {tipo}"
        )

    return " ".join(
        parte for parte in partes if parte
    )


# ------------------------------------------------------------
# HTML OFFLINE — SEM OPENSTREETMAP
# ------------------------------------------------------------

def criar_html(geojson):
    """Gera uma página web independente de servidores de tiles."""

    largura = 1200
    altura = 780
    limites = calcular_limites(geojson)

    cores = [
        "#e74c3c",
        "#3498db",
        "#2ecc71",
        "#9b59b6",
        "#f39c12",
        "#1abc9c",
        "#e67e22",
        "#16a085",
        "#8e44ad",
        "#27ae60",
        "#2980b9",
        "#c0392b",
        "#d35400",
        "#7f8c8d",
        "#34495e",
        "#f1c40f",
    ]

    caminhos = []

    for indice, feature in enumerate(
        geojson["features"]
    ):
        propriedades = feature["properties"]
        geometria = feature["geometry"]

        caminho = geometria_para_svg(
            geometria,
            limites,
            largura,
            altura,
        )

        codigo = escape(
            str(
                propriedades["codigo_ibge"]
            )
        )

        municipio = escape(
            str(
                propriedades["municipio"]
            )
        )

        populacao = int(
            propriedades["populacao"]
        )

        cor = cores[
            indice % len(cores)
        ]

        caminhos.append(
            f"""
            <path
                class="municipio"
                id="municipio-{codigo}"
                data-codigo="{codigo}"
                data-nome="{municipio}"
                data-populacao="{populacao}"
                d="{caminho}"
                fill="{cor}"
                tabindex="0"
            ></path>
            """
        )

    paths_html = "\n".join(caminhos)

    dados_json = json.dumps(
        geojson,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    total_populacao = sum(
        int(
            feature["properties"]["populacao"]
        )
        for feature in geojson["features"]
    )

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>
Mapa dos 92 Municípios do Rio de Janeiro
</title>

<style>
* {{
    box-sizing: border-box;
}}

html,
body {{
    width: 100%;
    height: 100%;
    margin: 0;
    overflow: hidden;
    font-family: Arial, Helvetica, sans-serif;
    background:
        linear-gradient(
            180deg,
            #8fd3ff 0%,
            #dff5ff 55%,
            #bde5bc 100%
        );
}}

#mapa {{
    position: absolute;
    inset: 0;
    width: 100vw;
    height: 100vh;
    cursor: grab;
    user-select: none;
}}

#mapa.arrastando {{
    cursor: grabbing;
}}

#grupoMapa {{
    transform-origin: center center;
}}

.municipio {{
    stroke: #ffffff;
    stroke-width: 1.05;
    stroke-linejoin: round;
    stroke-linecap: round;
    fill-opacity: 0.93;
    vector-effect: non-scaling-stroke;
    cursor: pointer;
    transition:
        fill 80ms linear,
        stroke 80ms linear;
}}

.municipio:hover,
.municipio:focus {{
    fill: #fff200 !important;
    stroke: #111111;
    stroke-width: 2.8;
    outline: none;
}}

#titulo {{
    position: fixed;
    z-index: 20;
    top: 14px;
    left: 50%;
    transform: translateX(-50%);
    width: min(700px, 88vw);
    padding: 14px 20px;
    text-align: center;
    background: rgba(255,255,255,0.97);
    border: 2px solid #1976d2;
    border-radius: 14px;
    box-shadow:
        0 4px 16px rgba(0,0,0,0.22);
    color: #163d63;
}}

#titulo .principal {{
    font-size: 23px;
    font-weight: bold;
}}

#titulo .secundario {{
    margin-top: 5px;
    font-size: 13px;
    color: #4d6980;
}}

#info {{
    position: fixed;
    z-index: 20;
    left: 17px;
    bottom: 17px;
    width: min(370px, 82vw);
    padding: 13px 15px;
    background: rgba(255,255,255,0.97);
    border: 1px solid #92b7d5;
    border-radius: 11px;
    box-shadow:
        0 3px 12px rgba(0,0,0,0.18);
    color: #28475e;
    font-size: 13px;
    line-height: 1.45;
}}

#controles {{
    position: fixed;
    z-index: 20;
    top: 115px;
    right: 18px;
    display: flex;
    flex-direction: column;
    gap: 6px;
}}

.controle {{
    width: 42px;
    height: 42px;
    border: 1px solid #9ab8cf;
    border-radius: 9px;
    background: rgba(255,255,255,0.96);
    color: #173d60;
    font-size: 22px;
    font-weight: bold;
    cursor: pointer;
    box-shadow:
        0 2px 8px rgba(0,0,0,0.18);
}}

.controle:hover {{
    background: #eaf5ff;
}}

#tooltip {{
    position: fixed;
    z-index: 100;
    display: none;
    min-width: 220px;
    max-width: 300px;
    pointer-events: none;
    padding: 12px 14px;
    border-radius: 11px;
    background: rgba(255,255,255,0.98);
    border: 2px solid #1976d2;
    box-shadow:
        0 4px 16px rgba(0,0,0,0.26);
    color: #183c5e;
}}

#tooltip .nome {{
    font-size: 17px;
    font-weight: bold;
}}

#tooltip .populacao {{
    margin-top: 5px;
    font-size: 14px;
}}

#tooltip .codigo {{
    margin-top: 3px;
    font-size: 11px;
    color: #70879b;
}}

#carregando {{
    position: fixed;
    z-index: 200;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #eaf6ff;
    color: #163d63;
    font-size: 20px;
    font-weight: bold;
}}

@media (max-width: 700px) {{
    #titulo .principal {{
        font-size: 18px;
    }}

    #titulo .secundario {{
        font-size: 11px;
    }}

    #info {{
        font-size: 11px;
    }}
}}
</style>
</head>

<body>

<div id="carregando">
    Preparando o mapa dos 92 municípios...
</div>

<div id="titulo">
    <div class="principal">
        Mapa dos 92 Municípios do Rio de Janeiro
    </div>

    <div class="secundario">
        Passe a seta sobre um município para visualizar
        seu nome e sua população.
    </div>
</div>

<div id="controles">
    <button
        class="controle"
        id="mais"
        title="Aumentar"
    >+</button>

    <button
        class="controle"
        id="menos"
        title="Diminuir"
    >−</button>

    <button
        class="controle"
        id="resetar"
        title="Voltar ao tamanho original"
    >⌂</button>
</div>

<div id="info">
    <b>Estado do Rio de Janeiro</b><br>
    92 municípios<br>
    População estimada pelo IBGE ({ANO_POPULACAO}):
    <b>{f"{total_populacao:,}".replace(",", ".")}</b><br>
    <span style="font-size:11px;">
        Referência: 01/07/{ANO_POPULACAO}
    </span>
</div>

<div id="tooltip">
    <div
        class="nome"
        id="tooltipNome"
    ></div>

    <div
        class="populacao"
        id="tooltipPopulacao"
    ></div>

    <div
        class="codigo"
        id="tooltipCodigo"
    ></div>
</div>

<svg
    id="mapa"
    viewBox="0 0 {largura} {altura}"
    preserveAspectRatio="xMidYMid meet"
    aria-label="Mapa dos 92 municípios do Rio de Janeiro"
>
    <g id="grupoMapa">
        <rect
            x="0"
            y="0"
            width="{largura}"
            height="{altura}"
            fill="#b9dfaa"
            opacity="0.30"
        ></rect>

        {paths_html}
    </g>
</svg>

<script>
const mapa = document.getElementById("mapa");
const grupo = document.getElementById("grupoMapa");
const tooltip = document.getElementById("tooltip");
const tooltipNome = document.getElementById("tooltipNome");
const tooltipPopulacao =
    document.getElementById("tooltipPopulacao");
const tooltipCodigo =
    document.getElementById("tooltipCodigo");

const caminhos =
    document.querySelectorAll(".municipio");

const larguraOriginal = {largura};
const alturaOriginal = {altura};

let escala = 1.0;
let deslocamentoX = 0;
let deslocamentoY = 0;

let arrastando = false;
let inicioX = 0;
let inicioY = 0;
let deslocamentoInicioX = 0;
let deslocamentoInicioY = 0;

function aplicarTransformacao() {{
    grupo.setAttribute(
        "transform",
        `translate(${{deslocamentoX}} ${{deslocamentoY}})
         scale(${{escala}})`
    );
}}

function formatarPopulacao(valor) {{
    return Number(valor).toLocaleString("pt-BR");
}}

function mostrarTooltip(evento, elemento) {{
    const nome =
        elemento.dataset.nome;

    const populacao =
        Number(
            elemento.dataset.populacao
        );

    const codigo =
        elemento.dataset.codigo;

    tooltipNome.textContent =
        nome;

    tooltipPopulacao.textContent =
        "População estimada: "
        + formatarPopulacao(populacao)
        + " habitantes";

    tooltipCodigo.textContent =
        "Código IBGE: " + codigo;

    tooltip.style.display =
        "block";

    moverTooltip(evento);
}}

function moverTooltip(evento) {{
    const margem = 16;
    const largura =
        tooltip.offsetWidth;
    const altura =
        tooltip.offsetHeight;

    let x =
        evento.clientX + 18;

    let y =
        evento.clientY + 18;

    if (
        x + largura
        >
        window.innerWidth - margem
    ) {{
        x =
            evento.clientX
            - largura
            - 18;
    }}

    if (
        y + altura
        >
        window.innerHeight - margem
    ) {{
        y =
            evento.clientY
            - altura
            - 18;
    }}

    tooltip.style.left =
        Math.max(
            margem,
            x
        ) + "px";

    tooltip.style.top =
        Math.max(
            margem,
            y
        ) + "px";
}}

function esconderTooltip() {{
    tooltip.style.display =
        "none";
}}

caminhos.forEach(
    elemento => {{

        elemento.addEventListener(
            "mouseenter",
            evento => {{
                mostrarTooltip(
                    evento,
                    elemento
                );
            }}
        );

        elemento.addEventListener(
            "mousemove",
            evento => {{
                moverTooltip(evento);
            }}
        );

        elemento.addEventListener(
            "mouseleave",
            () => {{
                esconderTooltip();
            }}
        );

        elemento.addEventListener(
            "focus",
            evento => {{
                mostrarTooltip(
                    evento,
                    elemento
                );
            }}
        );

        elemento.addEventListener(
            "blur",
            () => {{
                esconderTooltip();
            }}
        );
    }}
);

mapa.addEventListener(
    "mousedown",
    evento => {{
        if (
            evento.button !== 0
        ) {{
            return;
        }}

        arrastando = true;

        mapa.classList.add(
            "arrastando"
        );

        inicioX =
            evento.clientX;

        inicioY =
            evento.clientY;

        deslocamentoInicioX =
            deslocamentoX;

        deslocamentoInicioY =
            deslocamentoY;

        esconderTooltip();
    }}
);

window.addEventListener(
    "mousemove",
    evento => {{
        if (!arrastando) {{
            return;
        }}

        const dx =
            evento.clientX - inicioX;

        const dy =
            evento.clientY - inicioY;

        deslocamentoX =
            deslocamentoInicioX
            + dx;

        deslocamentoY =
            deslocamentoInicioY
            + dy;

        aplicarTransformacao();
    }}
);

window.addEventListener(
    "mouseup",
    () => {{
        arrastando = false;

        mapa.classList.remove(
            "arrastando"
        );
    }}
);

mapa.addEventListener(
    "wheel",
    evento => {{
        evento.preventDefault();

        const fator =
            evento.deltaY < 0
                ? 1.12
                : 0.89;

        const escalaAnterior =
            escala;

        escala =
            Math.min(
                5.0,
                Math.max(
                    0.55,
                    escala * fator
                )
            );

        const rect =
            mapa.getBoundingClientRect();

        const centroX =
            evento.clientX
            - rect.left;

        const centroY =
            evento.clientY
            - rect.top;

        const fatorReal =
            escala / escalaAnterior;

        deslocamentoX =
            centroX
            - fatorReal
            * (centroX - deslocamentoX);

        deslocamentoY =
            centroY
            - fatorReal
            * (centroY - deslocamentoY);

        aplicarTransformacao();
        esconderTooltip();
    }},
    {{
        passive: false
    }}
);

document.getElementById(
    "mais"
).addEventListener(
    "click",
    () => {{
        escala =
            Math.min(
                5.0,
                escala * 1.18
            );

        aplicarTransformacao();
    }}
);

document.getElementById(
    "menos"
).addEventListener(
    "click",
    () => {{
        escala =
            Math.max(
                0.55,
                escala * 0.85
            );

        aplicarTransformacao();
    }}
);

document.getElementById(
    "resetar"
).addEventListener(
    "click",
    () => {{
        escala = 1.0;
        deslocamentoX = 0;
        deslocamentoY = 0;

        aplicarTransformacao();
        esconderTooltip();
    }}
);

aplicarTransformacao();

document.getElementById(
    "carregando"
).style.display =
    "none";
</script>

</body>
</html>
"""

    ARQUIVO_HTML.write_text(
        html,
        encoding="utf-8",
    )


# ------------------------------------------------------------
# PROGRAMA PRINCIPAL
# ------------------------------------------------------------

def main():
    print("=" * 72)
    print(
        " MAPA WEB INTERATIVO — 92 MUNICÍPIOS "
        "DO RIO DE JANEIRO"
    )
    print("=" * 72)

    if sys.version_info < (3, 10):
        raise RuntimeError(
            "Use Python 3.10 ou superior."
        )

    try:
        print(
            "\n1/4 - Consultando os municípios "
            "diretamente no IBGE..."
        )

        municipios = obter_municipios()

        print(
            f"OK: {len(municipios)} municípios."
        )

        print(
            "\n2/4 - Consultando os limites "
            "geográficos no IBGE..."
        )

        geojson = obter_malha(
            municipios
        )

        print(
            f"OK: {len(geojson['features'])} geometrias."
        )

        print(
            "\n3/4 - Consultando a população "
            f"de {ANO_POPULACAO} no SIDRA/IBGE..."
        )

        populacao = obter_populacao()

        print(
            f"OK: {len(populacao)} populações."
        )

        print(
            "\n4/4 - Criando o mapa HTML "
            "SEM servidor de mapas externo..."
        )

        geojson_final = montar_geojson(
            municipios,
            geojson,
            populacao,
        )

        criar_html(
            geojson_final
        )

        print(
            "\nMapa criado com sucesso!"
        )

        print(
            f"Arquivo:\n{ARQUIVO_HTML}"
        )

        print(
            "\nAbrindo o navegador..."
        )

        # Abre o arquivo local. Como o mapa não depende
        # de tiles externos, ele continuará visível mesmo
        # depois que a página terminar de carregar.
        webbrowser.open(
            ARQUIVO_HTML.resolve().as_uri()
        )

        print(
            "\nPronto!"
        )

    except Exception as erro:
        print("\n" + "=" * 72)
        print("ERRO")
        print("=" * 72)
        print(erro)

        print(
            "\nInstale a única dependência com:"
        )

        print(
            "py -3.11 -m pip install --upgrade requests"
        )

        input(
            "\nPressione ENTER para fechar..."
        )


if __name__ == "__main__":
    main()
