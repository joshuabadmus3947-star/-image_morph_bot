"""
Image Morph Bot - Telegram Bot for Image Conversion
Convert images between PNG, JPEG, WEBP, BMP, TIFF, ICO, and GIF
"""

import os
import io
import logging
from pathlib import Path
from typing import Dict

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message,
    BufferedInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from PIL import Image
from dotenv import load_dotenv

# ==================== CONFIGURATION ====================

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set!")

BOT_NAME = "Image Morph Bot"
BOT_USERNAME = "image_morph_bot"
BOT_VERSION = "1.0.0"

storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

# ==================== CONSTANTS ====================

SUPPORTED_FORMATS: Dict[str, Dict[str, str]] = {
    "png": {"display": "PNG", "ext": ".png", "mime": "image/png"},
    "jpeg": {"display": "JPEG", "ext": ".jpg", "mime": "image/jpeg"},
    "webp": {"display": "WEBP", "ext": ".webp", "mime": "image/webp"},
    "bmp": {"display": "BMP", "ext": ".bmp", "mime": "image/bmp"},
    "tiff": {"display": "TIFF", "ext": ".tiff", "mime": "image/tiff"},
    "ico": {"display": "ICO", "ext": ".ico", "mime": "image/x-icon"},
    "gif": {"display": "GIF", "ext": ".gif", "mime": "image/gif"},
}

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_BATCH_SIZE = 20

# ==================== USER STATES ====================

class ConversionStates(StatesGroup):
    waiting_for_image = State()
    waiting_for_format_selection = State()
    waiting_for_batch = State()

user_data: Dict[int, Dict] = {}

# ==================== HELPERS ====================

def get_format_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    formats = list(SUPPORTED_FORMATS.keys())
    for i in range(0, len(formats), 3):
        row = []
        for fmt in formats[i:i+3]:
            display_name = SUPPORTED_FORMATS[fmt]["display"]
            row.append(InlineKeyboardButton(
                text=f"📷 {display_name}",
                callback_data=f"convert_to_{fmt}"
            ))
        builder.row(*row)
    builder.row(InlineKeyboardButton(
        text="❌ Cancel",
        callback_data="cancel_conversion"
    ))
    return builder.as_markup()


def convert_image(image_data: bytes, original_filename: str, target_format: str) -> tuple[bytes, str, str]:
    try:
        image = Image.open(io.BytesIO(image_data))
        format_info = SUPPORTED_FORMATS[target_format]
        ext = format_info["ext"]
        mime_type = format_info["mime"]
        base_name = Path(original_filename).stem
        new_filename = f"{base_name}_converted{ext}"
        output = io.BytesIO()

        if target_format == "ico":
            image = image.resize((64, 64))
            image.save(output, format="ICO", sizes=[(64, 64)])
        elif target_format == "gif":
            if image.mode not in ("P", "L", "RGB", "RGBA"):
                image = image.convert("RGB")
            image.save(output, format="GIF")
        elif target_format == "webp":
            image.save(output, format="WEBP", quality=85)
        elif target_format == "jpeg":
            if image.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", image.size, (255, 255, 255))
                if image.mode == "P":
                    image = image.convert("RGBA")
                if image.mode == "RGBA":
                    background.paste(image, mask=image.split()[-1])
                else:
                    background.paste(image)
                image = background
            elif image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            image.save(output, format="JPEG", quality=90)
        else:
            if image.mode not in ("RGB", "RGBA", "L"):
                image = image.convert("RGB")
            image.save(output, format=target_format.upper())

        output.seek(0)
        return output.read(), new_filename, mime_type
    except Exception as e:
        logger.error(f"Conversion error: {str(e)}")
        raise


async def send_converted_image(message: Message, image_data: bytes, original_filename: str, target_format: str):
    try:
        converted_data, new_filename, mime_type = convert_image(
            image_data, original_filename, target_format
        )
        input_file = BufferedInputFile(converted_data, filename=new_filename)
        await message.reply_document(
            document=input_file,
            caption=(
                f"✅ Conversion successful!\n\n"
                f"📁 Original: {original_filename}\n"
                f"🔄 Format: {target_format.upper()}\n"
                f"📊 Size: {len(converted_data) / 1024:.1f} KB\n\n"
                f"Send another image or use /help for options."
            )
        )
    except Exception as e:
        logger.error(f"Error sending converted image: {str(e)}")
        await message.reply(f"❌ Sorry, I couldn't convert this image: {str(e)}")


# ==================== COMMAND HANDLERS ====================

@dp.message(Command("start"))
async def start_command(message: Message):
    welcome_text = (
        f"🎨 Welcome to {BOT_NAME}!\n\n"
        "I convert images between different formats.\n"
        "Just send me any image and choose your format!\n\n"
        "📷 Supported formats:\n"
        "• PNG • JPEG • WEBP • BMP • TIFF • ICO • GIF\n\n"
        "📌 Commands:\n"
        "/start - Show this message\n"
        "/help - Show all commands\n"
        "/convert - Start a conversion\n"
        "/batch - Convert multiple images\n"
        "/formats - Show supported formats\n"
        "/about - About this bot\n"
        "/cancel - Cancel current operation\n\n"
        "💡 Tip: Just send an image to get started!"
    )
    await message.reply(welcome_text)


@dp.message(Command("help"))
async def help_command(message: Message):
    help_text = (
        "🤖 How to use Image Morph Bot:\n\n"
        "1️⃣ Send me any image (photo or file)\n"
        "2️⃣ Click on your preferred format\n"
        "3️⃣ I'll convert and send it back!\n\n"
        "📷 Supported formats:\n"
        "PNG, JPEG, WEBP, BMP, TIFF, ICO, GIF\n\n"
        "🔄 Commands:\n"
        "/start - Show welcome message\n"
        "/help - Show this help\n"
        "/convert - Start a new conversion\n"
        "/batch - Batch convert multiple images\n"
        "/formats - List all supported formats\n"
        "/about - About this bot\n"
        "/cancel - Cancel current operation\n\n"
        "⚡ Tips:\n"
        "• Send any image - photo, document, or sticker\n"
        "• I preserve image quality as much as possible\n"
        "• I handle transparent images (except JPEG)\n"
        f"• Batch up to {MAX_BATCH_SIZE} images at once"
    )
    await message.reply(help_text)


@dp.message(Command("convert"))
async def convert_command(message: Message, state: FSMContext):
    await state.set_state(ConversionStates.waiting_for_image)
    await message.reply(
        "📤 Please send me an image to convert.\n"
        "You can send it as a photo or as a file.\n\n"
        "Send /cancel to cancel."
    )


@dp.message(Command("formats"))
async def formats_command(message: Message):
    format_list = "\n".join([
        f"• {info['display']} (.{fmt})"
        for fmt, info in SUPPORTED_FORMATS.items()
    ])
    await message.reply(
        f"📷 Supported image formats:\n\n{format_list}\n\n"
        f"Total: {len(SUPPORTED_FORMATS)} formats"
    )


@dp.message(Command("about"))
async def about_command(message: Message):
    about_text = (
        f"🤖 {BOT_NAME}\n\n"
        f"Version: {BOT_VERSION}\n"
        "Built with: Python 3.11, aiogram 3.4.1, Pillow 10.4.0\n\n"
        "📷 Convert images between formats:\n"
        "PNG ↔ JPEG ↔ WEBP ↔ BMP ↔ TIFF ↔ ICO ↔ GIF\n\n"
        "🔒 Privacy: Images are processed and deleted immediately.\n"
        "No data is stored on our servers.\n\n"
        f"👨‍💻 Username: @{BOT_USERNAME}"
    )
    await message.reply(about_text)


@dp.message(Command("batch"))
async def batch_command(message: Message, state: FSMContext):
    await state.set_state(ConversionStates.waiting_for_batch)
    await message.reply(
        f"📚 Please send me the images you want to convert.\n"
        f"I'll ask for the format after you've sent them.\n\n"
        f"• You can send up to {MAX_BATCH_SIZE} images\n"
        "• Send /done when you're ready\n"
        "• Send /cancel to cancel"
    )


@dp.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_data:
        del user_data[user_id]
    await message.reply("✅ Operation cancelled.\nSend me an image or use /help for options.")


@dp.message(Command("done"))
async def done_command(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in user_data or "batch_images" not in user_data[user_id]:
        await message.reply("❌ No images found in batch.\nSend images first, then /done.")
        return
    images = user_data[user_id]["batch_images"]
    if not images:
        await message.reply("❌ No images to process.")
        return
    if len(images) > MAX_BATCH_SIZE:
        await message.reply(f"❌ Too many images! Maximum {MAX_BATCH_SIZE} images per batch.")
        return
    await state.set_state(ConversionStates.waiting_for_format_selection)
    user_data[user_id]["batch_mode"] = True
    await message.reply(
        f"📚 Found {len(images)} images in batch.\n\n"
        "Please select the format you want to convert them to:",
        reply_markup=get_format_keyboard()
    )


# ==================== IMAGE HANDLERS ====================

@dp.message(lambda message: message.photo or message.document)
async def handle_image(message: Message, state: FSMContext):
    user_id = message.from_user.id
    try:
        if message.photo:
            photo = message.photo[-1]
            file_id = photo.file_id
            original_filename = "image.jpg"
        elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
            file_id = message.document.file_id
            original_filename = message.document.file_name or "image.jpg"
        else:
            await message.reply("❌ Please send an image file.")
            return

        if hasattr(message, 'document') and message.document and message.document.file_size:
            if message.document.file_size > MAX_FILE_SIZE:
                await message.reply(f"❌ File too large! Maximum size: 10MB")
                return

        file = await bot.get_file(file_id)
        image_data = await bot.download_file(file.file_path)
        image_bytes = image_data.read() if hasattr(image_data, 'read') else image_data

        current_state = await state.get_state()

        if current_state == ConversionStates.waiting_for_batch.state:
            if user_id not in user_data:
                user_data[user_id] = {}
            if "batch_images" not in user_data[user_id]:
                user_data[user_id]["batch_images"] = []
            if len(user_data[user_id]["batch_images"]) >= MAX_BATCH_SIZE:
                await message.reply(f"❌ Batch limit reached! Maximum {MAX_BATCH_SIZE} images.")
                return
            user_data[user_id]["batch_images"].append({
                "data": image_bytes,
                "filename": original_filename
            })
            await message.reply(
                f"✅ Added: {original_filename}\n"
                f"Total: {len(user_data[user_id]['batch_images'])}/{MAX_BATCH_SIZE} images\n"
                "Send /done when you're ready to convert them."
            )
            return
        else:
            await state.set_state(ConversionStates.waiting_for_format_selection)
            if user_id not in user_data:
                user_data[user_id] = {}
            user_data[user_id]["image_data"] = image_bytes
            user_data[user_id]["filename"] = original_filename
            user_data[user_id]["batch_mode"] = False
            await message.reply(
                f"✅ Got your image: {original_filename}\n\n"
                "Select the format to convert to:",
                reply_markup=get_format_keyboard()
            )
    except Exception as e:
        logger.error(f"Error handling image: {str(e)}")
        await message.reply(f"❌ Error processing your image: {str(e)}")


# ==================== CALLBACK QUERY HANDLERS ====================

@dp.callback_query()
async def handle_callback(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    data = callback_query.data

    if data == "cancel_conversion":
        await state.clear()
        if user_id in user_data:
            del user_data[user_id]
        await callback_query.message.edit_text("❌ Conversion cancelled.")
        await callback_query.message.reply("Send me another image or use /help for options.")
        return

    if data.startswith("convert_to_"):
        target_format = data.replace("convert_to_", "")
        if target_format not in SUPPORTED_FORMATS:
            await callback_query.message.reply("❌ Invalid format selected.")
            return

        if user_id in user_data and user_data[user_id].get("batch_mode"):
            batch_images = user_data[user_id].get("batch_images", [])
            if not batch_images:
                await callback_query.message.reply("❌ No images found in batch.")
                return
            await callback_query.message.edit_text(
                f"⏳ Converting {len(batch_images)} images to {target_format.upper()}..."
            )
            converted_count = 0
            failed_count = 0
            for idx, img_data in enumerate(batch_images):
                try:
                    image_bytes = img_data["data"]
                    original_filename = img_data["filename"]
                    converted_data, new_filename, mime_type = convert_image(
                        image_bytes, original_filename, target_format
                    )
                    input_file = BufferedInputFile(converted_data, filename=new_filename)
                    await callback_query.message.reply_document(
                        document=input_file,
                        caption=f"✅ {idx+1}/{len(batch_images)}: {new_filename}"
                    )
                    converted_count += 1
                except Exception as e:
                    logger.error(f"Batch conversion error: {str(e)}")
                    failed_count += 1
                    await callback_query.message.reply(
                        f"❌ Failed to convert {img_data.get('filename', 'unknown')}: {str(e)}"
                    )
            if user_id in user_data:
                del user_data[user_id]
            await state.clear()
            await callback_query.message.edit_text(
                f"✅ Batch conversion complete!\n"
                f"✅ Converted: {converted_count}/{len(batch_images)}\n"
                f"❌ Failed: {failed_count}"
            )
        else:
            if user_id not in user_data or "image_data" not in user_data[user_id]:
                await callback_query.message.reply("❌ No image found. Please send an image first.")
                return
            image_data = user_data[user_id]["image_data"]
            original_filename = user_data[user_id]["filename"]
            await callback_query.message.edit_text(f"⏳ Converting to {target_format.upper()}...")
            try:
                await send_converted_image(
                    callback_query.message,
                    image_data,
                    original_filename,
                    target_format
                )
                if user_id in user_data:
                    del user_data[user_id]
                await state.clear()
                await callback_query.message.delete()
            except Exception as e:
                logger.error(f"Conversion error: {str(e)}")
                await callback_query.message.reply(f"❌ Conversion failed: {str(e)}")
                if user_id in user_data:
                    del user_data[user_id]
                await state.clear()


# ==================== MAIN ====================

async def main():
    try:
        logger.info("🚀 Image Morph Bot is starting...")
        logger.info(f"🤖 Username: @{BOT_USERNAME}")
        logger.info(f"📷 Supported formats: {', '.join(SUPPORTED_FORMATS.keys())}")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")
        raise
    finally:
        await bot.session.close()


if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
