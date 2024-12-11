import asyncio
from io import BytesIO
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError
from gemini_handler import generate_text, analyze_image
from conversation_manager import ConversationManager
from utils import is_user_allowed
from html_format import format_message
from PIL import Image
from config import SYSTEM_INSTRUCTION
from config import TELEGRAM_MSG_CHAR_LIMIT


conversation_manager = ConversationManager()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Xin chào! Tôi là bot Telegram được hỗ trợ bởi Gemini. Tôi có thể giúp gì cho bạn hôm nay?")

async def send_long_message(update: Update, text: str, parse_mode=None):
    parts = []
    current_part = ""
    
    for line in text.split('\n'):
        if len(current_part) + len(line) + 1 <= TELEGRAM_MSG_CHAR_LIMIT:
            current_part += line + '\n'
        else:
            if current_part:
                parts.append(current_part.strip())
            current_part = line + '\n'
    
    if current_part:
        parts.append(current_part.strip())

    first_message = None
    for i, part in enumerate(parts):
        try:
            if i == 0:
                first_message = await update.message.reply_text(part, parse_mode=parse_mode)
            else:
                await update.message.reply_text(part, parse_mode=parse_mode, reply_to_message_id=first_message.message_id)
            await asyncio.sleep(0.5)  # Tăng thời gian chờ giữa các tin nhắn
        except Exception as e:
            print(f"Lỗi khi gửi phần {i+1}: {e}")
    
    return first_message

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_user_allowed(update.effective_user.username):
        await update.message.reply_text("Xin lỗi, bạn không được phép sử dụng bot này.")
        return

    user_id = update.effective_user.id
    user_input = update.message.text

    conversation_manager.add_message(user_id, "user", user_input)
    history = conversation_manager.get_history(user_id)

    init_msg = await update.message.reply_text("Đang suy nghĩ...")

    try:
        response = generate_text(user_input, SYSTEM_INSTRUCTION, history)
        full_response = ""

        for chunk in response:
            if chunk.text:
                full_response += chunk.text
                
        formatted_response = format_message(full_response)
        await init_msg.delete()
        await send_long_message(update, formatted_response, parse_mode=ParseMode.HTML)

        conversation_manager.add_message(user_id, "model", full_response)

    except NetworkError:
        await update.message.reply_text("Có vẻ như mạng của bạn đang gặp vấn đề. Vui lòng thử lại sau.")
    except Exception as e:
        print(f"Đã xảy ra lỗi: {e}")
        await update.message.reply_text("Đã xảy ra lỗi trong quá trình xử lý. Vui lòng thử lại.")

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_user_allowed(update.effective_user.username):
        await update.message.reply_text("Xin lỗi, bạn không được phép sử dụng bot này.")
        return

    init_msg = await update.message.reply_text(
        text="Đang xử lý hình ảnh...",
        reply_to_message_id=update.message.message_id
    )

    file = await update.message.photo[-1].get_file()
    image_bytes = await file.download_as_bytearray()
    image = Image.open(BytesIO(image_bytes))

    prompt = update.message.caption if update.message.caption else "Phân tích hình ảnh này và tạo phản hồi"

    try:
        response = analyze_image(image, prompt)
        full_response = ""

        for chunk in response:
            if chunk.text:
                full_response += chunk.text
                formatted_response = format_message(full_response)
                
                if len(formatted_response) > TELEGRAM_MSG_CHAR_LIMIT:
                    await init_msg.delete()
                    await send_long_message(update, formatted_response, parse_mode=ParseMode.HTML)
                else:
                    try:
                        await init_msg.edit_text(formatted_response, parse_mode=ParseMode.HTML)
                    except BadRequest:
                        await init_msg.delete()
                        init_msg = await send_long_message(update, formatted_response, parse_mode=ParseMode.HTML)

            await asyncio.sleep(0.1)

        user_id = update.effective_user.id
        conversation_manager.add_message(user_id, "user", f"Đã gửi một hình ảnh với prompt: {prompt}")
        conversation_manager.add_message(user_id, "model", full_response)

    except NetworkError:
        await init_msg.edit_text("Có vẻ như mạng của bạn đang gặp vấn đề. Vui lòng thử lại sau.")
    except Exception as e:
        print(f"Đã xảy ra lỗi: {e}")
        await init_msg.edit_text("Đã xảy ra lỗi trong quá trình xử lý hình ảnh. Vui lòng thử lại.")

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_user_allowed(update.effective_user.username):
        await update.message.reply_text("Xin lỗi, bạn không được phép sử dụng bot này.")
        return

    user_id = update.effective_user.id
    conversation_manager.clear_history(user_id)
    await update.message.reply_text("Lịch sử hội thoại đã được xóa.")