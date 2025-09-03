import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from binance.client import Client
import requests
import json

# Настройки логирования чтобы видеть ошибки
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
BOT_TOKEN = "8141637379:AAEaCbFuH0PXtb8WHc4N06F1vM6h5XsJtw8"  # ЗАМЕНИТЕ НА СВОЙ ТОКЕН!

# Создаем клиент Binance (можно без API ключей)
client = Client()

async def get_p2p_price_binance():
    """
    Основная функция: получаем цену USDT/RUB с P2P Binance.
    Ищет по всем доступным методам оплаты.
    """
    try:
        # Широкие параметры поиска
        data = {
            "proMerchantAds": False,
            "page": 1,
            "rows": 20,
            "payTypes": [],  # Ищем по всем методам оплаты
            "countries": [],
            "publisherType": None,
            "fiat": "RUB",
            "tradeType": "BUY",
            "asset": "USDT",
            "transAmount": ""
        }

        response = requests.post(
            'https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search',
            headers={'Content-Type': 'application/json'},
            json=data,
            timeout=10
        )
        
        result = response.json()
        
        if not result['success'] or not result['data']:
            logger.warning("Binance P2P: no offers found")
            return None

        ads = result['data']
        prices = []

        # Собираем цены из доступных объявлений
        for ad in ads:
            try:
                adv_info = ad['adv']
                # Проверяем что объявление активно и есть доступный объем
                if (float(adv_info['surplusAmount']) > 0 and 
                    adv_info['tradeMethods'] and
                    adv_info['price']):
                    price = float(adv_info['price'])
                    prices.append(price)
            except (KeyError, ValueError):
                continue

        if prices:
            # Берем среднюю цену из топ-5 предложений
            top_prices = sorted(prices)[:5]
            average_price = sum(top_prices) / len(top_prices)
            logger.info(f"Binance P2P: found {len(prices)} offers, average price: {average_price}")
            return round(average_price, 2)
        else:
            logger.warning("Binance P2P: no valid offers found")
            return None

    except Exception as e:
        logger.error(f"Binance P2P error: {e}")
        return None

async def get_spot_price_binance():
    """
    Резервная функция: получаем цену USDT/RUB с спотового рынка Binance.
    """
    try:
        ticker = client.get_symbol_ticker(symbol="USDTRUB")
        usdt_rub_price = float(ticker['price'])
        logger.info(f"Binance Spot price: {usdt_rub_price}")
        return round(usdt_rub_price, 2)
    except Exception as e:
        logger.error(f"Binance Spot error: {e}")
        return None

async def get_price_coingecko():
    """
    Аварийная функция: получаем цену USDT/RUB с CoinGecko.
    """
    try:
        response = requests.get(
            'https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=rub',
            timeout=10
        )
        data = response.json()
        usdt_rub_price = data['tether']['rub']
        logger.info(f"CoinGecko price: {usdt_rub_price}")
        return usdt_rub_price
    except Exception as e:
        logger.error(f"CoinGecko error: {e}")
        return None

async def get_ton_price():
    """
    Функция для получения текущей цены TON к USDT.
    """
    try:
        ticker = client.get_symbol_ticker(symbol="TONUSDT")
        ton_price = float(ticker['price'])
        logger.info(f"TON price: {ton_price}")
        return ton_price
    except Exception as e:
        logger.error(f"TON price error: {e}")
        return None

async def get_usdt_rub_price():
    """
    Главная функция получения цены USDT/RUB.
    Пробует все методы по очереди до первого успешного.
    """
    price = await get_p2p_price_binance()
    if price is not None:
        return price, "P2P Binance"
    
    price = await get_spot_price_binance()
    if price is not None:
        return price, "Spot Binance"
    
    price = await get_price_coingecko()
    if price is not None:
        return price, "CoinGecko"
    
    return None, "No data"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет сообщение при получении команды /start"""
    user = update.effective_user
    await update.message.reply_html(
        rf"Привет {user.mention_html()}! 🤖\n\n"
        r"Я бот для отслеживания цены TON через P2P рынок.\n"
        r"Доступные команды:\n"
        r"• /price - текущая цена TON в рублях\n"
        r"• /convert <amount> - конвертация TON в рубли\n"
        r"Например: /convert 5.5"
    )

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет текущую цену TON в RUB"""
    await update.message.reply_chat_action(action="typing")
    
    usdt_rub_price, source = await get_usdt_rub_price()
    ton_usdt_price = await get_ton_price()

    if usdt_rub_price and ton_usdt_price:
        ton_rub_price = ton_usdt_price * usdt_rub_price
        message = (f"<b>💎 TON / RUB</b>\n\n"
                   f"• <b>1 TON</b> ≈ <b>{ton_rub_price:,.2f} ₽</b>\n"
                   f"• 1 USDT = {usdt_rub_price} ₽ ({source})\n"
                   f"• 1 TON = {ton_usdt_price:,.4f} $\n\n"
                   f"<i>Обновлено: {source}</i>")
    else:
        message = "😕 Не удалось получить данные от всех источников. Попробуйте позже."

    await update.message.reply_text(message, parse_mode='HTML')

async def convert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Конвертирует указанное количество TON в рубли"""
    await update.message.reply_chat_action(action="typing")
    
    if not context.args:
        await update.message.reply_text(
            "Пожалуйста, укажите количество TON. Например: `/convert 5.5`", 
            parse_mode='Markdown'
        )
        return

    try:
        amount = float(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "Пожалуйста, укажите корректное число. Например: `/convert 5.5`", 
            parse_mode='Markdown'
        )
        return

    usdt_rub_price, source = await get_usdt_rub_price()
    ton_usdt_price = await get_ton_price()

    if usdt_rub_price and ton_usdt_price:
        result = (amount * ton_usdt_price) * usdt_rub_price
        message = (f"<b>🧮 Конвертация</b>\n\n"
                   f"• <b>{amount} TON</b> ≈ <b>{result:,.2f} ₽</b>\n"
                   f"• Источник: {source}\n"
                   f"• Курс: 1 TON = {ton_usdt_price:,.4f} $\n"
                   f"• Курс: 1 USDT = {usdt_rub_price} ₽")
    else:
        message = "😕 Не удалось получить данные для конвертации. Попробуйте позже."

    await update.message.reply_text(message, parse_mode='HTML')

def main():
    """Запускает бота."""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("price", price))
    application.add_handler(CommandHandler("convert", convert))
    
    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()