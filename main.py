import os
import io
import logging
import tempfile
from pathlib import Path
from typing import Dict, Optional

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from PIL import Image
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set!")

# Initialize bot and dispatcher
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

# Supported image formats with their display names and file extensions
SUPPORTED_FORMATS: Dict[str, Dict[str, str]] = {
    "png": {"display": "PNG", "ext": ".png", "mime": "image/png"},
    "jpeg": {"display": "JPEG", "ext": ".jpg", "mime": "image/jpeg"},
    "webp": {"display": "WEBP", "ext": ".webp", "mime": "image/webp"},
    "bmp": {"display": "BMP", "ext": ".bmp", "mime": "image/bmp"},
    "tiff": {"display": "TIFF", "ext": ".tiff", "mime": "image/tiff"},
    "ico": {"display": "ICO", "ext": ".ico", "mime": "image/x-icon"},
    "gif": {"display": "GIF", "ext": ".gif", "mime": "image/gif"},
}

# User states
class ConversionStates(StatesGroup):
    waiting_for_image = State()
    waiting_for_format_selection = State()
    waiting_for_batch = State()

# Temporary storage for user data
user_data: Dict[int, Dict] = {}


# ==================== HELPERS ====================

def get_format_keyboard() -> InlineKeyboardMarkup:
    """Create inline keyboard with all supported formats"""
    builder = InlineKeyboardBuilder()
    
    # Create a grid with 3 buttons per row
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
    
    # Add cancel button at the bottom
    builder.row(InlineKeyboardButton(
        text="❌ Cancel",
        callback_data="cancel_conversion"
    ))
    
    return builder.as_markup()


def convert_image(
    image_data: bytes,
    original_filename: str,
    target_format: str
) -> tuple[bytes, str, str]:
    """
    Convert image to target format using PIL
    Returns: (converted_bytes, new_filename, mime_type)
    """
    try:
        # Open image from bytes
        image = Image.open(io.BytesIO(image_data))
        
        # Get format info
        format_info = SUPPORTED_FORMATS[target_format]
        ext = format_info["ext"]
        mime_type = format_info["mime"]
        
        # Generate new filename
        base_name = Path(original_filename).stem
        new_filename = f"{base_name}_converted{ext}"
        
        # Convert format
        output = io.BytesIO()
        
        # Handle special cases
        if target_format == "ico":
            # ICO format requires specific size handling
            image = image.resize((64, 64))
            image.save(output, format="ICO", sizes=[(64, 64)])
        elif target_format == "gif":
            # Convert to RGB for GIF if needed
            if image.mode not in ("P", "L", "RGB", "RGBA"):
                image = image.convert("RGB")
            image.save(output, format="GIF")
        elif target_format == "webp":
            image.save(output, format="WEBP", quality=85)
        elif target_format == "jpeg":
            # Convert to RGB if image has transparency (JPEG doesn't support alpha)
            if image.mode in ("RGBA", "LA", "P"):
                # Create a white background
                background = Image.new("RGB", image.size, (255, 255, 255))
                if image.mode == "P":
                    image = image.convert("RGBA")
                background.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
                image = background
            elif image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            image.save(output, format="JPEG", quality=90)
        else:
            # Default conversion for other formats
            if image.mode not in ("RGB", "RGBA", "L"):
                image = image.convert("RGB")
            image.save(output, format=target_format.upper())
        
        output.seek(0)
        return output.read(), new_filename, mime_type
        
    except Exception as e:
        logger.error(f"Conversion error: {str(e)}")
        raise


async def send_converted_image(
    message: types.Message,
    image_data: bytes,
    original_filename: str,
    target_format: str
) -> None:
    """Send converted image back to user"""
    try:
        converted_data, new_filename, mime_type = convert_image(
            image_data, original_filename, target_format
        )
        
        # Create InputFile from bytes
        from aiogram.types import BufferedInputFile
        input_file = BufferedInputFile(
            converted_data,
            filename=new_filename
        )
        
        # Send as document with thumbnail preview
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
        await message.reply(
            f"❌ Sorry, I couldn't convert this image: {str(e)}\n"
            f"Try another format or send a different image."
        )


# ==================== COMMAND HANDLERS ====================

@dp.message(Command("start"))
async def start_command(message: types.Message):
    """Handle /start command"""
    welcome_text = (
        "🎨 Welcome to Image Morph Bot!\n\n"
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
        "/about - About this bot\n\n"
        "💡 Tip: Just send an image to get started!"
    )
    
    await message.reply(welcome_text)


@dp.message(Command("help"))
async def help_command(message: types.Message):
    """Handle /help command"""
    help_text = (
        "🤖 How to use Image Morph Bot:\n\n"
        "1️⃣ Send me any image (photo or file)\n"
        "2️⃣ Click on your preferred format\n"
        "3️⃣ I'll convert and send it back!\n\n"
        "📷 Supported formats:\n"
        "PNG, JPEG, WEBP, BMP, TIFF, ICO, GIF\n\n"
        "🔄 Commands:\n"
        "/convert - Start a new conversion\n"
        "/batch - Batch convert images\n"
        "/formats - List all formats\n"
        "/about - About this bot\n"
        "/cancel - Cancel current operation\n\n"
        "⚡ Tips:\n"
        "• Send any image - photo, document, or sticker\n"
        "• I preserve image quality as much as possible\n"
        "• I handle transparent images (except JPEG)"
    )
    
    await message.reply(help_text)


@dp.message(Command("convert"))
async def convert_command(message: types.Message, state: FSMContext):
    """Handle /convert command"""
    await state.set_state(ConversionStates.waiting_for_image)
    await message.reply(
        "📤 Please send me an image to convert.\n"
        "You can send it as a photo or as a file.\n\n"
        "Send /cancel to cancel."
    )


@dp.message(Command("formats"))
async def formats_command(message: types.Message):
    """Show all supported formats"""
    format_list = "\n".join([
        f"• {info['display']} (.{fmt})"
        for fmt, info in SUPPORTED_FORMATS.items()
    ])
    
    await message.reply(
        f"📷 Supported image formats:\n\n{format_list}\n\n"
        f"Total: {len(SUPPORTED_FORMATS)} formats"
    )


@dp.message(Command("about"))
async def about_command(message: types.Message):
    """Show bot information"""
    about_text = (
        "🤖 Image Morph Bot\n\n"
        "Version: 1.0.0\n"
        "Built with: Python 3.11, aiogram 3.3.0, Pillow\n\n"
        "📷 Convert images between formats:\n"
        "PNG ↔ JPEG ↔ WEBP ↔ BMP ↔ TIFF ↔ ICO ↔ GIF\n\n"
        "🔒 Privacy: Images are processed and deleted immediately.\n"
        "No data is stored on our servers.\n\n"
        "👨‍💻 Open Source: Check the source code on GitHub\n"
        "@image_morph_bot"
    )
    
    await message.reply(about_text)


@dp.message(Command("batch"))
async def batch_command(message: types.Message, state: FSMContext):
    """Handle batch conversion"""
    await state.set_state(ConversionStates.waiting_for_batch)
    await message.reply(
        "📚 Please send me the images you want to convert.\n"
        "I'll ask for the format after you've sent them.\n\n"
        "• You can send multiple images\n"
        "• Send /done when you're ready\n"
        "• Send /cancel to cancel"
    )


@dp.message(Command("cancel"))
async def cancel_command(message: types.Message, state: FSMContext):
    """Cancel current operation"""
    await state.clear()
    
    # Clear user data
    if message.from_user.id in user_data:
        del user_data[message.from_user.id]
    
    await message.reply(
        "✅ Operation cancelled.\n"
        "Send me an image or use /help for options."
    )


@dp.message(Command("done"))
async def done_command(message: types.Message, state: FSMContext):
    """Process batch images"""
    user_id = message.from_user.id
    
    if user_id not in user_data or "batch_images" not in user_data[user_id]:
        await message.reply(
            "❌ No images found in batch.\n"
            "Send images first, then /done."
        )
        return
    
    images = user_data[user_id]["batch_images"]
    
    if not images:
        await message.reply("❌ No images to process.")
        return
    
    await state.set_state(ConversionStates.waiting_for_format_selection)
    
    # Store the batch for processing later
    user_data[user_id]["batch_mode"] = True
    
    await message.reply(
        f"📚 Found {len(images)} images in batch.\n\n"
        "Please select the format you want to convert them to:",
        reply_markup=get_format_keyboard()
    )


# ==================== IMAGE HANDLERS ====================

@dp.message(lambda message: message.photo or message.document)
async def handle_image(message: types.Message, state: FSMContext):
    """Handle incoming images"""
    user_id = message.from_user.id
    
    try:
        # Determine if it's a photo or document
        if message.photo:
            # Get the largest photo
            photo = message.photo[-1]
            file_id = photo.file_id
            original_filename = "image.jpg"
            file_type = "photo"
        elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
            # It's an image document
            file_id = message.document.file_id
            original_filename = message.document.file_name or "image.jpg"
            file_type = "document"
        else:
            # Not an image
            await message.reply(
                "❌ Please send an image file.\n"
                "I support PNG, JPEG, WEBP, BMP, TIFF, ICO, and GIF."
            )
            return
        
        # Download the image
        file = await bot.get_file(file_id)
        image_data = await bot.download_file(file.file_path)
        image_bytes = image_data.read() if hasattr(image_data, 'read') else image_data
        
        # Check current state
        current_state = await state.get_state()
        
        if current_state == ConversionStates.waiting_for_batch.state:
            # Add to batch
            if user_id not in user_data:
                user_data[user_id] = {}
            if "batch_images" not in user_data[user_id]:
                user_data[user_id]["batch_images"] = []
            
            user_data[user_id]["batch_images"].append({
                "data": image_bytes,
                "filename": original_filename
            })
            
            await message.reply(
                f"✅ Added: {original_filename}\n"
                f"Total: {len(user_data[user_id]['batch_images'])} images\n"
                "Send /done when you're ready to convert them."
            )
            return
        
        elif current_state == ConversionStates.waiting_for_image.state:
            # Single image conversion - ask for format
            await state.set_state(ConversionStates.waiting_for_format_selection)
            
            # Store the image data
            if user_id not in user_data:
                user_data[user_id] = {}
            user_data[user_id]["image_data"] = image_bytes
            user_data[user_id]["filename"] = original_filename
            
            await message.reply(
                f"✅ Got your image: {original_filename}\n\n"
                "Now select the format you want:",
                reply_markup=get_format_keyboard()
            )
            return
        
        else:
            # Default behavior - just convert
            await state.set_state(ConversionStates.waiting_for_format_selection)
            
            # Store the image data
            if user_id not in user_data:
                user_data[user_id] = {}
            user_data[user_id]["image_data"] = image_bytes
            user_data[user_id]["filename"] = original_filename
            
            await message.reply(
                f"✅ Got your image: {original_filename}\n\n"
                "Select the format to convert to:",
                reply_markup=get_format_keyboard()
            )
        
    except Exception as e:
        logger.error(f"Error handling image: {str(e)}")
        await message.reply(
            f"❌ Error processing your image: {str(e)}\n"
            "Please try again with a different image."
        )


# ==================== CALLBACK QUERY HANDLERS ====================

@dp.callback_query()
async def handle_callback(callback_query: CallbackQuery, state: FSMContext):
    """Handle inline keyboard callbacks"""
    await callback_query.answer()
    
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    # Handle cancel
    if data == "cancel_conversion":
        await state.clear()
        if user_id in user_data:
            del user_data[user_id]
        
        await callback_query.message.edit_text(
            "❌ Conversion cancelled."
        )
        await callback_query.message.reply(
            "Send me another image or use /help for options."
        )
        return
    
    # Handle format selection
    if data.startswith("convert_to_"):
        target_format = data.replace("convert_to_", "")
        
        if target_format not in SUPPORTED_FORMATS:
            await callback_query.message.reply("❌ Invalid format selected.")
            return
        
        # Check if we're in batch mode
        if user_id in user_data and user_data[user_id].get("batch_mode"):
            # Process batch conversion
            batch_images = user_data[user_id].get("batch_images", [])
            
            if not batch_images:
                await callback_query.message.reply("❌ No images found in batch.")
                return
            
            await callback_query.message.edit_text(
                f"⏳ Converting {len(batch_images)} images to {target_format.upper()}...\n"
                "This may take a moment."
            )
            
            # Convert each image
            converted_count = 0
            for idx, img_data in enumerate(batch_images):
                try:
                    image_bytes = img_data["data"]
                    original_filename = img_data["filename"]
                    
                    converted_data, new_filename, mime_type = convert_image(
                        image_bytes, original_filename, target_format
                    )
                    
                    # Send the converted image
                    from aiogram.types import BufferedInputFile
                    input_file = BufferedInputFile(converted_data, filename=new_filename)
                    
                    await callback_query.message.reply_document(
                        document=input_file,
                        caption=f"✅ {idx+1}/{len(batch_images)}: {new_filename}"
                    )
                    converted_count += 1
                    
                except Exception as e:
                    logger.error(f"Batch conversion error for {img_data.get('filename', 'unknown')}: {str(e)}")
                    await callback_query.message.reply(
                        f"❌ Failed to convert {img_data.get('filename', 'unknown')}: {str(e)}"
                    )
            
            # Clean up
            if user_id in user_data:
                del user_data[user_id]
            await state.clear()
            
            await callback_query.message.edit_text(
                f"✅ Batch conversion complete!\n"
                f"Converted {converted_count}/{len(batch_images)} images to {target_format.upper()}."
            )
            
        else:
            # Single image conversion
            if user_id not in user_data or "image_data" not in user_data[user_id]:
                await callback_query.message.reply(
                    "❌ No image found. Please send an image first."
                )
                return
            
            image_data = user_data[user_id]["image_data"]
            original_filename = user_data[user_id]["filename"]
            
            await callback_query.message.edit_text(
                f"⏳ Converting to {target_format.upper()}...\n"
                "Please wait."
            )
            
            try:
                # Convert and send
                await send_converted_image(
                    callback_query.message,
                    image_data,
                    original_filename,
                    target_format
                )
                
                # Clean up
                if user_id in user_data:
                    del user_data[user_id]
                await state.clear()
                
                await callback_query.message.delete()
                
            except Exception as e:
                logger.error(f"Conversion error: {str(e)}")
                await callback_query.message.reply(
                    f"❌ Conversion failed: {str(e)}\n"
                    "Please try again with a different image or format."
                )
                # Clean up on error
                if user_id in user_data:
                    del user_data[user_id]
                await state.clear()


# ==================== ERROR HANDLERS ====================

@dp.errors()
async def error_handler(update, exception):
    """Global error handler"""
    logger.error(f"Unhandled error: {str(exception)}")
    
    if hasattr(update, 'message') and update.message:
        try:
            await update.message.reply(
                "❌ An unexpected error occurred.\n"
                "Please try again or report this issue."
            )
        except:
            pass


# ==================== STARTUP ====================

async def on_startup():
    """Actions to perform when bot starts"""
    logger.info("🚀 Image Morph Bot is starting...")
    logger.info(f"📷 Supported formats: {', '.join(SUPPORTED_FORMATS.keys())}")
    logger.info("✅ Bot is ready!")


async def on_shutdown():
    """Actions to perform when bot stops"""
    logger.info("🛑 Image Morph Bot is shutting down...")


# ==================== MAIN ====================

async def main():
    """Main entry point"""
    try:
        # Register startup/shutdown handlers
        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)
        
        # Start polling
        logger.info("Starting bot polling...")
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
