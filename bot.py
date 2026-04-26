import os
import asyncio
import logging
import httpx
import re
from datetime import datetime
from telegram import Bot
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ══════════════════════════════════════
# CONFIGURAÇÕES
# ══════════════════════════════════════
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
NEWSDATA_KEY     = os.getenv("NEWSDATA_KEY")
HEYGEN_API_KEY   = os.getenv("HEYGEN_API_KEY")
HEYGEN_AVATAR_ID = os.getenv("HEYGEN_AVATAR_ID", "433ded8e7723432286d1dcd80963894a")
HEYGEN_VOICE_ID  = os.getenv("HEYGEN_VOICE_ID", "djx4PWJHhm5Nr7hhxVfS")
HORARIOS         = ["08:00", "14:00", "20:00"]

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("JoaoCriptoBot")
EMOJIS = ["🚀", "📈", "💰", "🔥", "⚡", "📰", "💡", "🧠", "👀", "🌐"]

def periodo_do_dia():
    h = datetime.now().hour
    if h < 12:  return "🌅 BOM DIA"
    if h < 18:  return "☀️ BOA TARDE"
    return "🌙 BOA NOITE"

async def buscar_noticias():
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://newsdata.io/api/1/news",
                params={"apikey": NEWSDATA_KEY, "q": "bitcoin OR cripto OR criptomoeda", "language": "pt", "category": "business,technology"}
            )
            r.raise_for_status()
            resultados = r.json().get("results", [])
            if not resultados:
                r2 = await client.get(
                    "https://newsdata.io/api/1/news",
                    params={"apikey": NEWSDATA_KEY, "q": "bitcoin OR crypto", "language": "en", "category": "business,technology"}
                )
                r2.raise_for_status()
                resultados = r2.json().get("results", [])
            return resultados[:3]
    except Exception as e:
        log.error(f"Erro noticias: {e}")
        return []

async def buscar_preco_btc():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "bitcoin", "vs_currencies": "brl,usd", "include_24hr_change": "true"}
            )
            r.raise_for_status()
            btc = r.json().get("bitcoin", {})
            return {"brl": btc.get("brl", 0), "usd": btc.get("usd", 0), "change": btc.get("brl_24h_change", 0)}
    except Exception as e:
        log.error(f"Erro preco: {e}")
        return None

def gerar_roteiro(noticia, preco):
    titulo = noticia.get("title", "")
    descricao = re.sub(r'<[^>]+>', '', noticia.get("description", "") or "")
    descricao = descricao[:200]
    preco_txt = ""
    if preco:
        sinal = "em alta" if preco["change"] >= 0 else "em queda"
        brl = f"R$ {preco['brl']:,.0f}".replace(",", ".")
        preco_txt = f"O Bitcoin está {sinal} hoje, valendo {brl}. "
    return f"""Fala pessoal, aqui é o João Cripto!

{preco_txt}

A notícia de hoje é: {titulo}.

{descricao}

Essa informação é importante porque mostra como o mercado cripto continua em movimento. Fique de olho e continue acumulando!

Acesse meu grupo no Telegram e use a calculadora DCA gratuita no link da bio para simular seus ganhos até a próxima ATH!

Os grandes pensam diferente. Até a próxima!""".strip()

async def criar_video_heygen(roteiro):
    headers = {"X-Api-Key": HEYGEN_API_KEY, "Content-Type": "application/json"}
    payload = {
        "video_inputs": [{"character": {"type": "avatar", "avatar_id": HEYGEN_AVATAR_ID, "avatar_style": "normal"}, "voice": {"type": "text", "input_text": roteiro, "voice_id": HEYGEN_VOICE_ID, "speed": 1.0}, "background": {"type": "color", "value": "#000000"}}],
        "dimension": {"width": 720, "height": 1280},
        "aspect_ratio": "9:16",
        "test": False
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post("https://api.heygen.com/v2/video/generate", headers=headers, json=payload)
            r.raise_for_status()
            video_id = r.json().get("data", {}).get("video_id")
            log.info(f"Video criado! ID: {video_id}")
            return video_id
    except Exception as e:
        log.error(f"Erro HeyGen: {e}")
        return None

async def aguardar_video(video_id, max_tentativas=30):
    headers = {"X-Api-Key": HEYGEN_API_KEY}
    for i in range(max_tentativas):
        await asyncio.sleep(20)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"https://api.heygen.com/v1/video_status.get?video_id={video_id}", headers=headers)
                r.raise_for_status()
                data = r.json().get("data", {})
                status = data.get("status")
                log.info(f"Status video ({i+1}/{max_tentativas}): {status}")
                if status == "completed":
                    return data.get("video_url")
                elif status == "failed":
                    return None
        except Exception as e:
            log.error(f"Erro status: {e}")
    return None

async def baixar_video(url_video):
    try:
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            r = await client.get(url_video)
            r.raise_for_status()
            return r.content
    except Exception as e:
        log.error(f"Erro download: {e}")
        return None

def limpar_html(texto):
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def montar_mensagem_texto(noticias, preco):
    periodo = periodo_do_dia()
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    if preco:
        sinal = "▲" if preco["change"] >= 0 else "▼"
        cor = "🟢" if preco["change"] >= 0 else "🔴"
        brl = f"R$ {preco['brl']:,.0f}".replace(",", ".")
        usd = f"US$ {preco['usd']:,.0f}".replace(",", ".")
        chg = f"{preco['change']:+.2f}%"
        linha_preco = f"{cor} <b>BTC:</b> {brl} ({usd}) {sinal} {chg} (24h)"
    else:
        linha_preco = "Preco indisponivel no momento"
    itens = ""
    for i, n in enumerate(noticias):
        titulo = limpar_html(n.get("title", "Sem titulo"))
        url = n.get("link") or n.get("source_url") or ""
        em = EMOJIS[i % len(EMOJIS)]
        itens += f'{em} <a href="{url}">{titulo}</a>\n\n' if url else f"{em} {titulo}\n\n"
    return f"""<b>JOAO CRIPTO {periodo}</b>
Data: {now} Brasilia

{linha_preco}

PRINCIPAIS NOTICIAS CRIPTO

{itens}
Dica Joao Cripto:
<i>Acumule todo dia. O tempo no mercado bate o timing.</i>

Calculadora DCA gratuita:
joao-cripto-btc.netlify.app

Os grandes pensam diferente!
#Bitcoin #Cripto #JoaoCripto #DCA #Halving2028"""

async def postar_noticias():
    log.info(f"Iniciando post — {datetime.now().strftime('%H:%M')}")
    bot = Bot(token=TELEGRAM_TOKEN)
    noticias = await buscar_noticias()
    preco = await buscar_preco_btc()
    if not noticias:
        log.warning("Sem noticias")
        return

    # Posta texto
    msg = montar_mensagem_texto(noticias, preco)
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        log.info("Texto enviado!")
    except Exception as e:
        log.error(f"Erro texto: {e}")

    # Gera e posta vídeo
    roteiro = gerar_roteiro(noticias[0], preco)
    log.info("Criando video no HeyGen...")
    video_id = await criar_video_heygen(roteiro)
    if not video_id:
        return
    log.info("Aguardando video ficar pronto...")
    url_video = await aguardar_video(video_id)
    if not url_video:
        return
    titulo = limpar_html(noticias[0].get("title", ""))
    log.info("Enviando video pelo URL direto...")
    try:
        # Envia pela URL direto — sem precisar baixar
        await bot.send_video(
            chat_id=TELEGRAM_CHAT_ID,
            video=url_video,
            caption=f"🎬 <b>{titulo}</b>\n\n#Bitcoin #JoaoCripto",
            parse_mode=ParseMode.HTML,
            supports_streaming=True
        )
        log.info("Video enviado!")
    except Exception as e:
        log.error(f"Erro URL direto: {e} — tentando download...")
        bytes_video = await baixar_video(url_video)
        if not bytes_video:
            return
        try:
            await bot.send_video(
                chat_id=TELEGRAM_CHAT_ID,
                video=bytes_video,
                caption=f"🎬 <b>{titulo}</b>\n\n#Bitcoin #JoaoCripto",
                parse_mode=ParseMode.HTML,
                supports_streaming=True
            )
            log.info("Video enviado via download!")
        except Exception as e2:
            log.error(f"Erro fatal video: {e2}")

async def main():
    log.info("Joao Cripto Bot iniciando...")
    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")
    for horario in HORARIOS:
        hora, minuto = horario.split(":")
        scheduler.add_job(postar_noticias, "cron", hour=int(hora), minute=int(minuto), id=f"post_{horario}")
        log.info(f"Agendado para {horario}")
    scheduler.start()
    log.info("Bot rodando!")
    await postar_noticias()
    while True:
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
