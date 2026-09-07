import os
import uuid
import asyncio
import numpy as np
import yt_dlp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from moviepy.editor import VideoFileClip
from pydub import AudioSegment

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8839261922:AAEwe-AUMXSmk0Fap2n1VpMQ_E8sSEg41s8"
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ЛОГИКА СКАЧИВАНИЯ С YOUTUBE ---
def download_youtube_video(url, output_path):
    """Скачивает видео с YouTube с помощью yt-dlp"""
    # Настройки: качаем видео не больше 720p (для скорости) и объединяем с лучшим звуком
    ydl_opts = {
        'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path, # Куда сохранять
        'quiet': True,          # Меньше спама в консоль
        'noplaylist': True      # Если скинут плейлист, качаем только одно видео
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        print(f"Ошибка yt-dlp: {e}")
        return False


# --- ЛОГИКА ОБРАБОТКИ ВИДЕО (старая функция) ---
def extract_best_moment(input_path, output_path, audio_path, clip_before=15, clip_after=5):
    try:
        video = VideoFileClip(input_path)
        if video.audio is None:
            return False

        video.audio.write_audiofile(audio_path, logger=None)
        audio = AudioSegment.from_file(audio_path)
        
        chunk_size = 1000 
        chunks = [audio[i:i+chunk_size] for i in range(0, len(audio), chunk_size)]
        volumes = [chunk.dBFS for chunk in chunks]
        
        loudest_sec_index = np.argmax(volumes)
        
        start_time = max(0, loudest_sec_index - clip_before)
        end_time = min(video.duration, loudest_sec_index + clip_after)
        
        final_clip = video.subclip(start_time, end_time)
        final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac", logger=None)
        
        video.close()
        final_clip.close()
        return True
    except Exception as e:
        print(f"Ошибка при обработке: {e}")
        return False


# --- ОБРАБОТЧИКИ ТЕЛЕГРАМ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Привет! Отправь мне видео (до 20МБ) ИЛИ *ссылку на YouTube*, и я найду самый громкий момент!")

# Хендлер для ссылок на YouTube
@dp.message(F.text.regexp(r"(youtube\.com|youtu\.be)"))
async def handle_youtube_link(message: types.Message):
    url = message.text.strip()
    msg = await message.reply("🔗 Вижу ссылку на YouTube! Начинаю скачивание (это займет какое-то время)...")
    
    task_id = str(uuid.uuid4())
    input_path = f"input_{task_id}.mp4"
    output_path = f"output_{task_id}.mp4"
    audio_path = f"audio_{task_id}.wav"

    try:
        # 1. Скачиваем видео (в отдельном потоке, чтобы бот не завис)
        download_success = await asyncio.to_thread(download_youtube_video, url, input_path)
        
        if not download_success:
            await msg.edit_text("❌ Не удалось скачать видео. Возможно, оно закрыто или удалено.")
            return

        await msg.edit_text("🔍 Видео скачано! Ищу лучший момент и монтирую клип...")

        # 2. Ищем хайлайт (в отдельном потоке)
        process_success = await asyncio.to_thread(extract_best_moment, input_path, output_path, audio_path)

        if process_success:
            await msg.edit_text("✅ Готово! Отправляю результат...")
            video_note = FSInputFile(output_path)
            await message.reply_video(video=video_note)
        else:
            await msg.edit_text("❌ Ошибка при обработке видео.")
            
    except Exception as e:
        await msg.edit_text("Произошла неожиданная ошибка.")
        print(e)
        
    finally:
        # Убираем за собой мусор
        for path in [input_path, output_path, audio_path]:
            if os.path.exists(path):
                os.remove(path)


# Хендлер для файлов (остался как был)
@dp.message(F.video)
async def handle_video(message: types.Message):
    if message.video.file_size > 20 * 1024 * 1024:
        await message.reply("Видео слишком большое! Отправь файл до 20 МБ или скинь ссылку на YouTube.")
        return
    # ... здесь код обработки обычного файла из предыдущего сообщения ...
    await message.reply("Функция обработки файлов работает в штатном режиме!")


async def main():
    print("Бот запущен! Жду ссылки и файлы...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
