#\!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Manhwa Translator - Telegram Bot
Send manga images -> get Thai translation back.
Supports: profiles, genre presets, auto glossary, batch mode.

Commands:
  /start          - Welcome + help
  /help           - Show all commands
  /setkey <key>   - Set Gemini API key
  /model <name>   - Set Gemini model
  /profile        - Show current profile
  /profiles       - List all profiles
  /newprofile <n>  - Create new profile
  /select <name>  - Select profile
  /delprofile <n>  - Delete profile
  /genre          - Show genre list
  /setgenre <n>   - Set genre (number)
  /glossary       - Show current glossary
  /clearglossary  - Clear glossary
  /save           - Save glossary to profile

Usage: Just send an image or multiple images\!
"""
import os, sys, json, re, io, zipfile, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
except ImportError:
    print("pip install google-generativeai")
    sys.exit(1)

try:
    from telegram import Update
    from telegram.ext import (
        Application, CommandHandler, MessageHandler,
        filters, ContextTypes, CallbackQueryHandler
    )
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
except ImportError:
    print("pip install python-telegram-bot")
    sys.exit(1)

from PIL import Image

try:
    from sheets_sync import pull_glossary_from_sheet, push_glossary_to_sheet, extract_sheet_id
    SHEETS_AVAILABLE = True
except ImportError:
    SHEETS_AVAILABLE = False

# ============================================================
# CONFIG
# ============================================================
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_data")
os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_MODEL = "gemini-3.1-pro-preview"
NOVEL_CHUNK_SIZE = 3000  # chars per translation chunk

GENRE_PRESETS = {
    "ไม่ระบุ (ทั่วไป)": "",
    "มูริม / กำลังภายใน": "แนวเรื่อง: มูริม/กำลังภายใน\nคำศัพท์: 내공=พลังภายใน, 무공=วิทยายุทธ์, 경맥=เส้นลมปราณ, 기=ชี่, 단전=ตันเถียน, 협객=จอมยุทธ์, 문파=สำนัก, 장문인=หัวหน้าสำนัก, 무림맹=สมาพันธ์ยุทธภพ, 사파=ฝ่ายมาร, 정파=ฝ่ายธรรม, 검법=กระบี่ศาสตร์, 권법=มวยศาสตร์, 비급=คัมภีร์ลับ, 초식=ท่า/กระบวนท่า, 경공=วิชาตัวเบา, 혈=จุดสกัด\nน้ำเสียง: ภาษาจีนกำลังภายใน/ยุคโบราณ",
    "แฟนตาซี / อิเซไก": "แนวเรื่อง: แฟนตาซี/อิเซไก\nคำศัพท์: 마나=มานา, 마법=เวทมนตร์, 스킬=สกิล, 던전=ดันเจี้ยน, 기사=อัศวิน, 용사=ผู้กล้า, 마왕=จอมมาร, 전생=เกิดใหม่, 회귀=ย้อนเวลา, 각성=ตื่นรู้, 레벨업=เลเวลอัป\nน้ำเสียง: ภาษาแฟนตาซีสมัยใหม่",
    "ระบบเกม / ฮันเตอร์": "แนวเรื่อง: ระบบเกม/ฮันเตอร์\nคำศัพท์: 시스템=ระบบ, 상태창=หน้าต่างสถานะ, 스킬=สกิล, 아이템=ไอเท็ม, 던전=ดันเจี้ยน, 헌터=ฮันเตอร์, 각성자=ผู้ตื่นรู้, 랭크=แรงค์\nน้ำเสียง: ภาษาสมัยใหม่ผสมศัพท์เกม",
    "ยุคกลาง / อัศวิน": "แนวเรื่อง: ยุคกลาง/อัศวิน\nคำศัพท์: 기사=อัศวิน, 영주=เจ้าเมือง, 황제=จักรพรรดิ, 왕=กษัตริย์, 기사단=กองอัศวิน, 성=ปราสาท\nน้ำเสียง: ภาษาสุภาพแบบราชสำนัก",
    "โรแมนซ์ / วังหลวง": "แนวเรื่อง: โรแมนซ์/วังหลวง\nคำศัพท์: 폐하=ฝ่าบาท, 전하=พระองค์, 황후=จักรพรรดินี, 상궁=ซังกุง, 양반=ยังบัน\nน้ำเสียง: ภาษาสุภาพ โรแมนติก",
    "สมัยใหม่ / โรงเรียน": "แนวเรื่อง: สมัยใหม่/โรงเรียน\nคำศัพท์: 선배=รุ่นพี่, 후배=รุ่นน้อง, 오빠=โอปป้า, 형=ฮยอง\nน้ำเสียง: ภาษาวัยรุ่นสมัยใหม่",
    "แอ็คชั่น / มาเฟีย": "แนวเรื่อง: แอ็คชั่น/มาเฟีย\nคำศัพท์: 두목=หัวหน้าแก๊ง, 보스=บอส, 형님=พี่ใหญ่\nน้ำเสียง: ภาษาห้าว ดิบ",
    "Sci-Fi / อนาคต": "แนวเรื่อง: Sci-Fi/อนาคต\nคำศัพท์: 우주선=ยานอวกาศ, 안드로이드=แอนดรอยด์, 차원=มิติ\nน้ำเสียง: ภาษาสมัยใหม่ผสมเทคโนโลยี",
}
GENRE_LIST = list(GENRE_PRESETS.keys())

# (display_name, instruction injected into prompt)
PRONOUN_PRESETS = [
    ("อัตโนมัติ (ตามบริบท)", ""),
    ("สมัยใหม่ — ฉัน/คุณ/นาย/เธอ",
     "สรรพนาม: ใช้ ฉัน/คุณ/นาย/เธอ/แก เป็นหลักตลอดเรื่อง ห้ามใช้ ข้า/เจ้า/ท่าน"),
    ("ทางการ — ผม/ดิฉัน/คุณ/ท่าน",
     "สรรพนาม: ใช้ ผม/ดิฉัน/คุณ/ท่าน เป็นหลักตลอดเรื่อง"),
    ("โบราณ/วัง — ข้า/เจ้า/ท่าน",
     "สรรพนาม: ใช้ ข้า/เจ้า/ท่าน/พระองค์ ตามสมัยโบราณ/ราชสำนัก"),
    ("กันเอง — กู/มึง/แก/มัน",
     "สรรพนาม: ใช้ กู/มึง/แก/มัน สำหรับตัวละครที่พูดกันเอง"),
    ("กำลังภายใน — ข้า/ท่าน/พวกเจ้า",
     "สรรพนาม: ใช้ ข้า/ท่าน/พวกเจ้า/อาจารย์ แบบนิยายกำลังภายใน"),
]

PROMPT_SINGLE = """คุณเป็นผู้เชี่ยวชาญแปลมังงะ/มันฮวาเป็นไทย (ตรวจจับภาษาอัตโนมัติ)
งาน: 1.OCR ข้อความจากภาพ ตามลำดับ panel บนลงล่าง 2.แปลเป็นไทย 3.สร้าง Glossary
กฎ: แปลตาม panel บนลงล่าง, ภาษาไทยธรรมชาติ, ทับศัพท์ชื่อเฉพาะ, SFX แปลเป็นไทย, คั่น speech bubble ด้วยบรรทัดว่าง
รูปแบบ output:
[บรรทัดแปลเรียงตาม panel]

[ข้อมูลตัวละครและชื่อเฉพาะ]
- ชื่อต้นฉบับ: [ต้นฉบับ], ชื่อแปล: [ไทย], คำอธิบาย: [เพศ (บทบาท) รายละเอียด]

สำคัญ: [ข้อมูลตัวละครและชื่อเฉพาะ] ต้องอยู่ท้ายเสมอ"""

PROMPT_NOVEL = """[SYSTEM PROMPT START]

[ROLE — บทบาทของคุณ]
คุณคือบรรณาธิการและนักแปลนิยายระดับปรมาจารย์ ผู้มีประสบการณ์แปลนิยายมากกว่า 20 ปี
เชี่ยวชาญทั้งภาษาเกาหลี ภาษาจีน ภาษาอังกฤษ ภาษาญี่ปุ่น และภาษาไทยในระดับเจ้าของภาษา
คุณเป็นที่รู้จักในวงการว่าสามารถถ่ายทอดจิตวิญญาณของต้นฉบับได้อย่างครบถ้วนสมบูรณ์
ราวกับนักเขียนเจ้าของภาษาไทยเป็นผู้เรียบเรียงเอง

[MISSION — ภารกิจ]
แปลข้อความต่อไปนี้จากภาษาต้นทาง (ตรวจจับอัตโนมัติ) เป็นภาษาไทย
โดยรักษาอรรถรส น้ำเสียง ลีลาการเขียน ความหมายโดยนัย และอารมณ์ของต้นฉบับให้ครบถ้วน

═══════════════════════════════════════════
[CORE RULES — กฎเหล็ก 7 ข้อ]
═══════════════════════════════════════════

กฎข้อ 1: ความถูกต้อง 100%
- ห้ามบิดเบือน ตกหล่น ตีความคลาดเคลื่อน หรือเพิ่มเติมเนื้อหาที่ไม่มีในต้นฉบับ
- แปลทุกบรรทัด ทุกประโยค ทุกคำพูด รวมถึงเสียงเอฟเฟกต์และคำอุทาน
- ห้ามแปลแบบหุ่นยนต์ (Machine Translation) เด็ดขาด

กฎข้อ 2: ไม่เซ็นเซอร์
- แปลคำสแลง คำหยาบ คำด่า ตามต้นฉบับอย่างซื่อสัตย์
- ฉากที่ล่อแหลมให้สรุปอย่างมีชั้นเชิง ใช้คำที่สื่อความหมายได้ครบ
  โดยไม่หยาบโลนจนเกินไป แต่ก็ไม่ตัดทิ้ง

กฎข้อ 3: ธรรมชาติของภาษาไทย
- หลีกเลี่ยงการแปลตรงตัวจนอึดอัด
- ใช้สำนวนไทยที่เหมาะสม สื่ออารมณ์เดียวกับต้นฉบับ
- ประโยคต้องลื่นไหล สละสลวย อ่านแล้วเป็นนิยายไทยจริงๆ

กฎข้อ 4: รักษาเสียงตัวละคร
- ตัวละครแต่ละตัวต้องมีวิธีพูดเป็นเอกลักษณ์
  (คนหยาบ พูดหยาบ / คนสุภาพ พูดสุภาพ / คนแก่ ใช้คำโบราณ ฯลฯ)
- ระดับภาษาต้องสอดคล้องกับฐานะ อายุ และบุคลิกของตัวละคร
- บทพูดต้องเป็นธรรมชาติ ไม่แข็งทื่อ อ่านแล้วเห็นภาพ "คนจริง" กำลังพูด

กฎข้อ 5: อารมณ์และบรรยากาศ
- ถ่ายทอดอารมณ์ฉาก (ตื่นเต้น เศร้า โรแมนติก ขบขัน สยองขวัญ ฯลฯ)
  ให้ผู้อ่านรู้สึก "อิน" เหมือนอ่านต้นฉบับ
- ฉากบู๊ → ใช้คำกระชับ จังหวะเร็ว สร้างความเร้าใจ
- ฉากโรแมนติก → ใช้คำหวาน อ่อนโยน สร้างบรรยากาศ
- ฉากดราม่า → ใช้คำหนักแน่น กินใจ สะเทือนอารมณ์
- ฉากตลก → ใช้คำคม มุกที่คนไทยเข้าใจ จังหวะตลกต้องไม่หาย

กฎข้อ 6: โครงสร้างและรูปแบบ
- คงลำดับบทพูด คำบรรยาย ความคิดในใจ ตามต้นฉบับ
- แยกย่อหน้า เว้นวรรค ตามต้นฉบับ
- เพิ่มบรรทัดว่างระหว่างย่อหน้าเพื่อความอ่านง่ายแบบ Novel
- เสียงเอฟเฟกต์ (SFX) ปรับให้เป็นธรรมชาติในภาษาไทย
  เช่น 쾅! → ปัง! / ドキドキ → ตุบๆ ตุบๆ / Crash! → กร๊าก!

กฎข้อ 7: คำศัพท์เฉพาะและชื่อ
- ชื่อตัวละคร: ทับศัพท์ตามการออกเสียงต้นฉบับ
  (เกาหลี: ใช้ระบบ ก-ฮ ที่คนไทยคุ้น / จีน: ใช้เสียงจีนกลาง / ญี่ปุ่น: ทับศัพท์ตามเสียง)
- ชื่อท่าไม้ตาย/สกิล: แปลความหมาย + วงเล็บชื่อต้นฉบับ ครั้งแรกที่ปรากฏ
  เช่น กระบี่เทพสังหาร (신살검법)
- ชื่อสถานที่/องค์กร: แปลความหมายถ้าแปลได้ มิฉะนั้นทับศัพท์
- คำศัพท์แฟนตาซี/จีนกำลังภายใน: ใช้คำไทยที่คุ้นเคยในแวดวงนิยาย
  เช่น 내공 → พลังภายใน / 무림 → ยุทธภพ / 검기 → ดาบพลัง
- ถ้า GLOSSARY กำหนดไว้แล้ว ให้ใช้ตามนั้นเท่านั้น ห้ามเปลี่ยนแปลง

═══════════════════════════════════════════
[ADVANCED TECHNIQUES — เทคนิคขั้นสูง]
═══════════════════════════════════════════

[A] การจัดการสำนวนเฉพาะวัฒนธรรม
- สำนวนเกาหลี/จีน/ญี่ปุ่นที่มีสำนวนไทยเทียบเคียง → ใช้สำนวนไทย
  เช่น 식은 죽 먹기 → "ง่ายเหมือนปอกกล้วยเข้าปาก"
- สำนวนที่ไม่มีคำเทียบ → แปลความหมาย แทรกเชิงอรรถถ้าจำเป็น
- วัฒนธรรมเฉพาะ (อาหาร เทศกาล ธรรมเนียม) → อธิบายสั้นๆ ในวงเล็บถ้าคนไทยอาจไม่เข้าใจ

[B] การจัดการระดับคำเรียกขาน (Honorifics)
- เกาหลี: 형/오빠/누나/언니 → พี่ (ปรับตามบริบท) / 선배 → รุ่นพี่ / 님 → ท่าน/คุณ
- จีน: 师父 → อาจารย์/ซือฝู / 大哥 → พี่ใหญ่ / 前辈 → รุ่นพี่/ผู้อาวุโส
- ญี่ปุ่น: さん → คุณ / 先輩 → รุ่นพี่ / 殿 → ท่าน
- ปรับให้เข้ากับบริบทและความสัมพันธ์ตัวละคร

[C] การจัดการ Onomatopoeia
- เกาหลี: 두근두근 → ตุบตุบ / 펑 → ปัง / 쿵 → ตูม
- จีน: 轰 → ตูม / 嘶 → ซี่ / 哗啦 → กร๊าก
- ญี่ปุ่น: ゴゴゴ → บรรยากาศคุกคาม (ใช้คำบรรยายแทน)
- ปรับให้เป็นธรรมชาติในภาษาไทย

[D] Inner Monologue / Thoughts
- ความคิดในใจ: ใช้เครื่องหมายตามต้นฉบับ
- แยกให้ชัดระหว่างคำพูดจริงกับความคิดในใจ
- น้ำเสียงความคิดในใจมักเป็นกันเอง ภาษาพูด ใช้คำย่อได้

[E] Narrator Voice
- บุคคลที่ 1 → ใช้ ข้า/ผม/ฉัน ตามบุคลิกตัวเอก
- บุคคลที่ 3 → ภาษาเป็นทางการกว่าบทพูดเล็กน้อย แต่ไม่แข็งทื่อ
- Omniscient → ภาษาสละสลวย ใช้คำวรรณศิลป์ได้

═══════════════════════════════════════════
[OUTPUT FORMAT — รูปแบบผลลัพธ์]
═══════════════════════════════════════════

1. แปลข้อความทั้งหมดเป็นภาษาไทย จัดรูปแบบเหมือนนิยายไทย
2. เว้นบรรทัดว่างระหว่างย่อหน้า (สไตล์ Novel Online)
3. ถ้ามีเชิงอรรถ → รวบรวมไว้ท้ายบท
4. ท้ายสุดของผลลัพธ์ ถ้ามีชื่อตัวละคร ท่าสกิล หรือชื่อเฉพาะปรากฏ
   ให้สรุปในรูปแบบนี้ (ห้ามใส่ ** เด็ดขาด):

[ข้อมูลตัวละครและชื่อเฉพาะ]
- ชื่อต้นฉบับ: (ชื่อภาษาต้นทาง), ชื่อแปล: (ชื่อภาษาไทย), คำอธิบาย: (เพศ/บทบาท/ข้อมูลสำคัญ)

ถ้าไม่มีชื่อเฉพาะปรากฏ ไม่ต้องสรุป

═══════════════════════════════════════════
[METADATA — ข้อมูลประกอบการแปล]
═══════════════════════════════════════════

ตอนที่: {{chunk_number}}
มุมมอง/ผู้เล่า: ตรวจจับอัตโนมัติจากเนื้อหา
ยุคสมัย: ตรวจจับอัตโนมัติจากเนื้อหา
แนวเรื่อง: {{genre_info}}

[GLOSSARY — คำศัพท์กำหนดไว้ล่วงหน้า]
(ห้ามเปลี่ยนแปลงหรือแก้ไขคำแปลเหล่านี้เด็ดขาด)
{{glossary_lines}}

═══════════════════════════════════════════
[FINAL REMINDER — ย้ำเป้าหมาย]
═══════════════════════════════════════════

ต้องการคำแปลระดับปรมาจารย์
- อ่านแล้วไม่สะดุด ไม่รู้สึกว่าเป็นงานแปล
- เข้าใจง่าย ได้อรรถรสครบถ้วน
- ตัวละครมีชีวิตชีวาผ่านคำพูดของพวกเขา
- ผู้อ่านต้องรู้สึกเหมือนอ่านนิยายไทยชั้นยอดเรื่องหนึ่ง

[SYSTEM PROMPT END]"""


# ============================================================
# USER DATA (per chat)
# ============================================================
def get_user_file(user_id):
    return os.path.join(DATA_DIR, f"user_{user_id}.json")

def load_user(user_id):
    path = get_user_file(user_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "api_key": "",
        "model": DEFAULT_MODEL,
        "genre": "ไม่ระบุ (ทั่วไป)",
        "current_profile": None,
        "profiles": {},
        "titles": [],
        "current_title": None,
    }

def save_user(user_id, data):
    with open(get_user_file(user_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_glossary(user_data):
    """Get current glossary from active profile or empty."""
    prof = user_data.get("current_profile")
    if prof and prof in user_data.get("profiles", {}):
        return user_data["profiles"][prof].get("glossary", {})
    return {}

def set_glossary(user_data, glossary):
    prof = user_data.get("current_profile")
    if prof and prof in user_data.get("profiles", {}):
        user_data["profiles"][prof]["glossary"] = glossary

def get_custom_prompt(user_data):
    prof = user_data.get("current_profile")
    if prof and prof in user_data.get("profiles", {}):
        return user_data["profiles"][prof].get("custom_prompt", "")
    return ""

def set_custom_prompt(user_data, prompt):
    prof = user_data.get("current_profile")
    if prof and prof in user_data.get("profiles", {}):
        user_data["profiles"][prof]["custom_prompt"] = prompt

def get_pronoun_style(user_data):
    prof = user_data.get("current_profile")
    if prof and prof in user_data.get("profiles", {}):
        return user_data["profiles"][prof].get("pronoun_style", "")
    return ""

def set_pronoun_style(user_data, style):
    prof = user_data.get("current_profile")
    if prof and prof in user_data.get("profiles", {}):
        user_data["profiles"][prof]["pronoun_style"] = style

def get_novel_context(user_data):
    """Get rolling context (tail of last translated output) for continuity."""
    prof = user_data.get("current_profile")
    if prof and prof in user_data.get("profiles", {}):
        return user_data["profiles"][prof].get("novel_context", "")
    return ""

def set_novel_context(user_data, context):
    prof = user_data.get("current_profile")
    if prof and prof in user_data.get("profiles", {}):
        user_data["profiles"][prof]["novel_context"] = context


def split_novel_text(text, max_chars=NOVEL_CHUNK_SIZE):
    """Split novel text into chunks at natural paragraph boundaries."""
    paragraphs = re.split(r'\n{2,}', text.strip())
    chunks, current, current_len = [], [], 0
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if current and current_len + len(para) + 2 > max_chars:
            chunks.append("\n\n".join(current))
            current, current_len = [para], len(para)
        else:
            current.append(para)
            current_len += len(para) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks or [text.strip()]


def translate_novel_chunk(text, api_key, model_name, genre_ctx, glossary,
                           custom_ctx="", prev_context="", chunk_num=1, pronoun_ctx=""):
    """Translate a novel text chunk with rolling context for continuity."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    # Format glossary for prompt
    if glossary:
        glossary_lines = "\n".join(
            f"- {orig} → {info['translated']} ({info.get('description', '')})"
            for orig, info in glossary.items()
        )
    else:
        glossary_lines = "(ยังไม่มี — ตรวจจับและเพิ่มอัตโนมัติระหว่างแปล)"

    genre_info = genre_ctx if genre_ctx else "ตรวจจับอัตโนมัติ"

    sys_prompt = PROMPT_NOVEL.replace("{{chunk_number}}", str(chunk_num)) \
                              .replace("{{genre_info}}", genre_info) \
                              .replace("{{glossary_lines}}", glossary_lines)

    if pronoun_ctx:
        sys_prompt += f"\n\n[กำกับสรรพนาม — บังคับใช้ตลอดการแปล]\n{pronoun_ctx}"
    if custom_ctx:
        sys_prompt += f"\n\n[คำแนะนำพิเศษสำหรับเรื่องนี้]\n{custom_ctx}"

    parts = []
    if prev_context:
        parts.append(
            f"[บริบทจากตอนที่แปลไปแล้ว — ใช้รักษาความต่อเนื่องของน้ำเสียงและชื่อตัวละคร]\n"
            f"{prev_context}\n[--- จบบริบท ---]\n"
        )
    parts.append(f"แปลข้อความต่อไปนี้:\n\n{text}")

    response = model.generate_content(
        [{"role": "user", "parts": [sys_prompt, "\n".join(parts)]}],
        generation_config=genai.GenerationConfig(temperature=0.3, max_output_tokens=8192),
        request_options={"timeout": 180},
    )
    full = response.text.strip()
    marker = "[ข้อมูลตัวละครและชื่อเฉพาะ]"
    if marker in full:
        idx = full.index(marker)
        return full[:idx].strip(), full[idx:].strip()
    return full, ""

def parse_glossary(text, existing):
    """Parse glossary from response text, merge with existing."""
    glossary = dict(existing)
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("[") or line.startswith("#"):
            continue
        m = re.search(r'ชื่อต้นฉบับ:\s*(.+?),\s*ชื่อแปล:\s*(.+?),\s*คำอธิบาย:\s*(.+)', line)
        if m:
            orig, trans, desc = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            if orig and trans:
                if orig in glossary:
                    if len(desc) > len(glossary[orig].get("description", "")):
                        glossary[orig]["description"] = desc
                    glossary[orig]["translated"] = trans
                else:
                    glossary[orig] = {"translated": trans, "description": desc}
    return glossary

def format_glossary_context(glossary):
    if not glossary:
        return ""
    lines = ["[Glossary - use consistently:]"]
    for o, d in glossary.items():
        lines.append(f"- ชื่อต้นฉบับ: {o}, ชื่อแปล: {d['translated']}, คำอธิบาย: {d['description']}")
    return "\n".join(lines)


def _pronoun_label(user_data):
    """Return display name of current pronoun preset."""
    style = get_pronoun_style(user_data)
    for name, instruction in PRONOUN_PRESETS:
        if instruction == style:
            return name
    return "อัตโนมัติ (ตามบริบท)"


def _settings_text(data):
    model = data.get("model", DEFAULT_MODEL)
    genre = data.get("genre", "ไม่ระบุ (ทั่วไป)")
    prof = data.get("current_profile") or "None"
    gloss = get_glossary(data)
    custom = get_custom_prompt(data)
    lines = [
        f"Model: {model}",
        f"Genre: {genre}",
        f"Profile: {prof}",
        f"Glossary: {len(gloss)} entries",
    ]
    if data.get("titles"):
        title = data.get("current_title") or "ยังไม่เลือก"
        lines.append(f"เรื่อง: {title}")
    if data.get("current_profile"):
        pronoun = _pronoun_label(data)
        if pronoun != "อัตโนมัติ (ตามบริบท)":
            lines.append(f"สรรพนาม: {pronoun}")
    if custom:
        lines.append(f"Custom prompt: {len(custom)} chars")
    lines.append("\nแก้ settings หรือกด Translate เลย")
    return "\n".join(lines)


def _settings_buttons(data):
    rows = [
        [InlineKeyboardButton("Translate", callback_data="tr:go")],
        [
            InlineKeyboardButton("Model", callback_data="tr:model"),
            InlineKeyboardButton("Genre", callback_data="tr:genre"),
        ],
    ]
    if data.get("titles"):
        title = data.get("current_title") or "เลือกชื่อเรื่อง..."
        rows.append([InlineKeyboardButton(f"📖 {title}", callback_data="tr:title")])
    if data.get("current_profile"):
        pronoun = _pronoun_label(data)
        rows.append([InlineKeyboardButton(f"💬 {pronoun}", callback_data="tr:pronouns")])
        custom = get_custom_prompt(data)
        label = "✏️ Prompt (set)" if custom else "✏️ Prompt"
        rows.append([InlineKeyboardButton(label, callback_data="tr:prompt")])
    return InlineKeyboardMarkup(rows)


# ============================================================
# GEMINI TRANSLATION
# ============================================================
def translate_image_bytes(img_bytes, api_key, model_name, genre_ctx, glossary_ctx,
                          custom_ctx="", pronoun_ctx=""):
    """Translate image bytes. Returns (text, glossary_section)."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    sys_prompt = PROMPT_SINGLE
    if genre_ctx:
        sys_prompt += "\n\n" + genre_ctx
    if pronoun_ctx:
        sys_prompt += "\n\n[กำกับสรรพนาม]\n" + pronoun_ctx
    if custom_ctx:
        sys_prompt += "\n\n[คำแนะนำพิเศษสำหรับเรื่องนี้]\n" + custom_ctx
    parts = []
    if glossary_ctx:
        parts.append(glossary_ctx + "\n")
    parts.append("OCR+แปลภาพนี้เป็นไทย พร้อม [ข้อมูลตัวละครและชื่อเฉพาะ] ท้ายสุด")
    user_prompt = "\n".join(parts)

    image_part = {"mime_type": "image/jpeg", "data": img_bytes}
    response = model.generate_content(
        [{"role": "user", "parts": [sys_prompt, image_part, user_prompt]}],
        generation_config=genai.GenerationConfig(temperature=0.3, max_output_tokens=4096),
        request_options={"timeout": 120}
    )
    full = response.text.strip()

    marker = "[ข้อมูลตัวละครและชื่อเฉพาะ]"
    if marker in full:
        idx = full.index(marker)
        return full[:idx].strip(), full[idx:].strip()
    return full, ""


# ============================================================
# BOT HANDLERS
# ============================================================
HELP_TEXT = """*Manhwa Translator Bot*

*ส่งภาพมังงะ* -> ได้คำแปลภาษาไทยกลับมา

*คำสั่งทั่วไป:*
/setkey `<api_key>` - ตั้ง Gemini API Key
/model - เลือก model (แสดงปุ่มเลือก)
/status - ดูการตั้งค่าปัจจุบัน

*Profile (แยกตามเรื่อง):*
/profiles - ดูรายชื่อ profile
/newprofile `<ชื่อเรื่อง>` - สร้าง profile ใหม่
/select `<ชื่อเรื่อง>` - เลือก profile
/delprofile `<ชื่อเรื่อง>` - ลบ profile

*แนวเรื่อง:*
/genre - ดูรายการแนวเรื่อง
/setgenre `<หมายเลข>` - ตั้งแนวเรื่อง

*Glossary:*
/glossary - ดู glossary ปัจจุบัน
/clearglossary - ล้าง glossary
/save - บันทึก glossary ลง profile

*Google Sheets:*
/setsheet `<URL or ID>` - เชื่อม Google Sheet
/setsheetname `<name>` - ตั้งชื่อ sheet tab
/sync - ดึง glossary จาก Sheet
/pushsheet - ส่ง glossary ไป Sheet

*ชื่อเรื่อง (สำหรับบันทึก Sheet):*
/addtitle `<ชื่อ>` - เพิ่มชื่อเรื่อง
/titles - ดูและเลือกชื่อเรื่อง
/deltitle `<ชื่อ>` - ลบชื่อเรื่อง

*Custom Prompt (per profile):*
/setprompt `<คำแนะนำ>` - ตั้ง instruction พิเศษสำหรับ profile นี้
/prompt - ดู custom prompt ปัจจุบัน
/clearprompt - ลบ custom prompt

*Novel Mode (แปลนิยาย):*
ส่งไฟล์ `.txt` → bot แบ่ง chunk อัตโนมัติ แปลต่อเนื่องหลายตอน
/resetnovel - ล้าง context (เริ่มนิยายเรื่องใหม่)

*วิธีใช้:*
1. /setkey ตั้ง API Key
2. /newprofile สร้าง profile
3. /setgenre เลือกแนว
4. /addtitle เพิ่มชื่อเรื่อง
5. ส่งรูปมังงะ → เลือกชื่อเรื่อง → แปล → บันทึก Sheet อัตโนมัติ\!"""


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "สวัสดี\! ส่งภาพมังงะมาได้เลย แปลให้อัตโนมัติ\n\n"
        "เริ่มต้น: /setkey <Gemini API Key>\n"
        "ดูคำสั่งทั้งหมด: /help"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

async def cmd_setkey(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    args = ctx.args
    if not args:
        await update.message.reply_text("Usage: /setkey <your_gemini_api_key>")
        return
    data = load_user(uid)
    key = args[0].strip("<>\"' ")
    data["api_key"] = key
    save_user(uid, data)
    masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
    await update.message.reply_text(f"API Key saved: {masked}")

AVAILABLE_MODELS = [
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.0-flash",
    "gemini-2.5-flash-preview-04-17",
    "gemini-2.5-pro-preview-03-25",
]

async def cmd_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_user(uid)
    if ctx.args:
        data["model"] = ctx.args[0]
        save_user(uid, data)
        await update.message.reply_text(f"Model set to: {data['model']}")
        return
    current = data.get("model", DEFAULT_MODEL)
    buttons = []
    for m in AVAILABLE_MODELS:
        label = f"{'>> ' if m == current else ''}{m}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"model:{m}")])
    kb = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(f"Current: {current}\nSelect model:", reply_markup=kb)

async def callback_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.data.startswith("model:"):
        return
    model_name = query.data[6:]
    uid = query.from_user.id
    data = load_user(uid)
    data["model"] = model_name
    save_user(uid, data)
    await query.edit_message_text(f"Model set to: {model_name}")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_user(uid)
    key_status = "Set" if data.get("api_key") else "Not set"
    prof = data.get("current_profile", "None")
    genre = data.get("genre", "ไม่ระบุ")
    gloss = get_glossary(data)
    await update.message.reply_text(
        f"API Key: {key_status}\n"
        f"Model: {data.get('model', DEFAULT_MODEL)}\n"
        f"Profile: {prof}\n"
        f"Genre: {genre}\n"
        f"Glossary: {len(gloss)} entries"
    )

async def cmd_profiles(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_user(uid)
    profiles = data.get("profiles", {})
    current = data.get("current_profile")
    if not profiles:
        await update.message.reply_text("No profiles yet. Create one: /newprofile <name>")
        return
    lines = ["Profiles:"]
    for name, info in profiles.items():
        g = info.get("glossary", {})
        marker = " <- active" if name == current else ""
        lines.append(f"  {name} ({len(g)} glossary){marker}")
    await update.message.reply_text("\n".join(lines))

async def cmd_newprofile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not ctx.args:
        await update.message.reply_text("Usage: /newprofile <series_name>")
        return
    name = " ".join(ctx.args)
    data = load_user(uid)
    if "profiles" not in data:
        data["profiles"] = {}
    data["profiles"][name] = {"genre": data.get("genre", "ไม่ระบุ (ทั่วไป)"), "glossary": {}}
    data["current_profile"] = name
    save_user(uid, data)
    await update.message.reply_text(f"Created & selected profile: {name}")

async def cmd_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not ctx.args:
        await update.message.reply_text("Usage: /select <profile_name>")
        return
    name = " ".join(ctx.args)
    data = load_user(uid)
    if name not in data.get("profiles", {}):
        await update.message.reply_text(f"Profile '{name}' not found. /profiles to see list")
        return
    data["current_profile"] = name
    prof_data = data["profiles"][name]
    data["genre"] = prof_data.get("genre", data.get("genre"))
    save_user(uid, data)
    gloss = prof_data.get("glossary", {})
    await update.message.reply_text(f"Selected: {name}\nGenre: {data['genre']}\nGlossary: {len(gloss)} entries")

async def cmd_delprofile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not ctx.args:
        await update.message.reply_text("Usage: /delprofile <profile_name>")
        return
    name = " ".join(ctx.args)
    data = load_user(uid)
    if name in data.get("profiles", {}):
        del data["profiles"][name]
        if data.get("current_profile") == name:
            data["current_profile"] = None
        save_user(uid, data)
        await update.message.reply_text(f"Deleted: {name}")
    else:
        await update.message.reply_text(f"Profile '{name}' not found")

async def cmd_genre(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lines = ["Genre presets:"]
    for i, name in enumerate(GENRE_LIST):
        lines.append(f"  {i}. {name}")
    lines.append("\nUsage: /setgenre <number>")
    await update.message.reply_text("\n".join(lines))

async def cmd_setgenre(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not ctx.args:
        await cmd_genre(update, ctx)
        return
    try:
        idx = int(ctx.args[0])
        if 0 <= idx < len(GENRE_LIST):
            data = load_user(uid)
            data["genre"] = GENRE_LIST[idx]
            # Also update profile genre
            prof = data.get("current_profile")
            if prof and prof in data.get("profiles", {}):
                data["profiles"][prof]["genre"] = GENRE_LIST[idx]
            save_user(uid, data)
            await update.message.reply_text(f"Genre set: {GENRE_LIST[idx]}")
        else:
            await update.message.reply_text(f"Invalid number. Use 0-{len(GENRE_LIST)-1}")
    except ValueError:
        await update.message.reply_text("Usage: /setgenre <number>")

async def cmd_glossary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_user(uid)
    gloss = get_glossary(data)
    if not gloss:
        await update.message.reply_text("Glossary is empty")
        return
    lines = [f"Glossary ({len(gloss)} entries):"]
    for orig, info in list(gloss.items())[:50]:
        lines.append(f"  {orig} -> {info['translated']}: {info['description']}")
    if len(gloss) > 50:
        lines.append(f"  ... and {len(gloss)-50} more")
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n..."
    await update.message.reply_text(text)

async def cmd_clearglossary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_user(uid)
    set_glossary(data, {})
    save_user(uid, data)
    await update.message.reply_text("Glossary cleared")

async def cmd_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_user(uid)
    prof = data.get("current_profile")
    if not prof:
        await update.message.reply_text("No profile selected. /newprofile <name> first")
        return
    save_user(uid, data)
    gloss = get_glossary(data)
    await update.message.reply_text(f"Saved: {prof} ({len(gloss)} glossary entries)")


# ============================================================
# GOOGLE SHEETS COMMANDS
# ============================================================
async def cmd_setsheet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not ctx.args:
        await update.message.reply_text(
            "Usage: /setsheet <Google Sheet URL or ID>\n\n"
            "Sheet must be 'Anyone with the link can view'\n"
            "Columns: Manga_Title | Original_Name | Translated_Name | description"
        )
        return
    data = load_user(uid)
    sheet_input = ctx.args[0]
    data["sheet_id"] = extract_sheet_id(sheet_input) if SHEETS_AVAILABLE else sheet_input
    save_user(uid, data)
    await update.message.reply_text(f"Sheet ID saved: {data['sheet_id']}")


async def cmd_sync(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Pull glossary from Google Sheet for current profile."""
    if not SHEETS_AVAILABLE:
        await update.message.reply_text("sheets_sync module not available")
        return
    uid = update.effective_user.id
    data = load_user(uid)
    sheet_id = data.get("sheet_id")
    if not sheet_id:
        await update.message.reply_text("Set sheet first: /setsheet <URL or ID>")
        return
    prof = data.get("current_profile")
    if not prof:
        await update.message.reply_text("Select a profile first: /newprofile or /select")
        return
    msg = await update.message.reply_text(f"Pulling glossary for '{prof}'...")
    try:
        sheet_name = data.get("sheet_name")
        entries = pull_glossary_from_sheet(sheet_id, prof, sheet_name)
        glossary = get_glossary(data)
        glossary.update(entries)
        set_glossary(data, glossary)
        save_user(uid, data)
        await msg.edit_text(f"Pulled {len(entries)} entries from Sheet for '{prof}'\nTotal glossary: {len(glossary)} entries")
    except Exception as e:
        await msg.edit_text(f"Error: {e}")


async def cmd_pushsheet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Push glossary to Google Sheet (requires credentials.json)."""
    if not SHEETS_AVAILABLE:
        await update.message.reply_text("sheets_sync module not available")
        return
    uid = update.effective_user.id
    data = load_user(uid)
    sheet_id = data.get("sheet_id")
    if not sheet_id:
        await update.message.reply_text("Set sheet first: /setsheet <URL or ID>")
        return
    prof = data.get("current_profile")
    if not prof:
        await update.message.reply_text("Select a profile first")
        return
    glossary = get_glossary(data)
    if not glossary:
        await update.message.reply_text("Glossary is empty")
        return
    creds_path = os.path.join(DATA_DIR, "credentials.json")
    if not os.path.exists(creds_path):
        await update.message.reply_text(
            "Push requires credentials.json (Google Service Account)\n"
            f"Place it in: {DATA_DIR}/credentials.json\n\n"
            "Pull (/sync) works without credentials if sheet is public."
        )
        return
    manga_title = data.get("current_title") or prof
    msg = await update.message.reply_text(f"Pushing glossary for '{manga_title}'...")
    try:
        sheet_name = data.get("sheet_name")
        count = push_glossary_to_sheet(sheet_id, manga_title, glossary, creds_path, sheet_name)
        await msg.edit_text(f"Pushed {count} new entries to Sheet for '{manga_title}'")
    except Exception as e:
        await msg.edit_text(f"Error: {e}")


async def cmd_setsheetname(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_user(uid)
    if not ctx.args:
        current = data.get("sheet_name", "(default: first sheet)")
        await update.message.reply_text(f"Current sheet name: {current}\nUsage: /setsheetname <name>")
        return
    name = " ".join(ctx.args)
    data["sheet_name"] = name
    save_user(uid, data)
    await update.message.reply_text(f"Sheet name set: {name}")


# ============================================================
# TITLE MANAGEMENT
# ============================================================
async def cmd_addtitle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not ctx.args:
        await update.message.reply_text("Usage: /addtitle <ชื่อเรื่อง>")
        return
    name = " ".join(ctx.args)
    data = load_user(uid)
    titles = data.get("titles", [])
    if name in titles:
        await update.message.reply_text(f"'{name}' มีอยู่แล้ว")
        return
    titles.append(name)
    data["titles"] = titles
    if not data.get("current_title"):
        data["current_title"] = name
    save_user(uid, data)
    await update.message.reply_text(f"เพิ่ม '{name}' แล้ว ({len(titles)} เรื่อง)")


async def cmd_titles(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_user(uid)
    titles = data.get("titles", [])
    current = data.get("current_title")
    if not titles:
        await update.message.reply_text("ยังไม่มีชื่อเรื่อง\nเพิ่มด้วย: /addtitle <ชื่อเรื่อง>")
        return
    buttons = []
    for i, t in enumerate(titles):
        mark = " ◀" if t == current else ""
        buttons.append([InlineKeyboardButton(f"{t}{mark}", callback_data=f"tts:{i}")])
    await update.message.reply_text(
        f"ชื่อเรื่องทั้งหมด ({len(titles)}) — กดเพื่อเลือก:\nลบด้วย /deltitle <ชื่อ>",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cmd_deltitle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not ctx.args:
        await update.message.reply_text("Usage: /deltitle <ชื่อเรื่อง>")
        return
    name = " ".join(ctx.args)
    data = load_user(uid)
    titles = data.get("titles", [])
    if name not in titles:
        await update.message.reply_text(f"ไม่พบ '{name}'")
        return
    titles.remove(name)
    data["titles"] = titles
    if data.get("current_title") == name:
        data["current_title"] = titles[0] if titles else None
    save_user(uid, data)
    await update.message.reply_text(f"ลบ '{name}' แล้ว")


async def cmd_setprompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_user(uid)
    if not data.get("current_profile"):
        await update.message.reply_text("เลือก profile ก่อน: /newprofile หรือ /select")
        return
    if not ctx.args:
        await update.message.reply_text(
            "Usage: /setprompt <คำแนะนำ>\n\n"
            "ตัวอย่าง:\n"
            "/setprompt ใช้สรรพนาม ข้า/ท่าน ตลอด\n"
            "/setprompt ตัวเอกชื่อ จอน แปลว่า จอนซอนอู ทับศัพท์เสมอ\n"
            "/setprompt น้ำเสียงเป็นทางการ สุภาพ ไม่ใช้คำสแลง"
        )
        return
    prompt = " ".join(ctx.args)
    set_custom_prompt(data, prompt)
    save_user(uid, data)
    prof = data.get("current_profile")
    await update.message.reply_text(f"ตั้ง custom prompt สำหรับ [{prof}] แล้ว:\n\"{prompt}\"")


async def cmd_prompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_user(uid)
    prof = data.get("current_profile")
    if not prof:
        await update.message.reply_text("เลือก profile ก่อน")
        return
    custom = get_custom_prompt(data)
    if custom:
        await update.message.reply_text(f"Custom prompt [{prof}]:\n\"{custom}\"\n\nลบด้วย /clearprompt")
    else:
        await update.message.reply_text(
            f"Custom prompt [{prof}]: ยังไม่ได้ตั้ง\n\nตั้งด้วย /setprompt <คำแนะนำ>"
        )


async def cmd_clearprompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_user(uid)
    if not data.get("current_profile"):
        await update.message.reply_text("เลือก profile ก่อน")
        return
    set_custom_prompt(data, "")
    save_user(uid, data)
    await update.message.reply_text("ลบ custom prompt แล้ว")


async def callback_tts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Select title from /titles list."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    idx = int(query.data[4:])
    data = load_user(uid)
    titles = data.get("titles", [])
    if idx >= len(titles):
        await query.edit_message_text("ไม่พบชื่อเรื่อง")
        return
    data["current_title"] = titles[idx]
    save_user(uid, data)
    current = titles[idx]
    buttons = []
    for i, t in enumerate(titles):
        mark = " ◀" if t == current else ""
        buttons.append([InlineKeyboardButton(f"{t}{mark}", callback_data=f"tts:{i}")])
    await query.edit_message_text(
        f"เลือก: {current}\nชื่อเรื่องทั้งหมด ({len(titles)}) — กดเพื่อเลือก:\nลบด้วย /deltitle <ชื่อ>",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ============================================================
# IMAGE HANDLER - Show settings before translating
# ============================================================
_pending_images = {}
_pending_novels = {}   # uid -> {"chunks": [...], "filename": "...", "char_count": int}
_stop_novel = set()    # uids that requested stop


def _novel_preview_text(data, filename, char_count, chunk_count):
    model = data.get("model", DEFAULT_MODEL)
    genre = data.get("genre", "ไม่ระบุ (ทั่วไป)")
    prof = data.get("current_profile") or "None"
    title = data.get("current_title") or "ไม่ระบุ"
    prev_ctx = get_novel_context(data)
    custom = get_custom_prompt(data)
    pronoun = _pronoun_label(data)
    return (
        f"📖 Novel mode\n"
        f"ไฟล์: {filename}\n"
        f"ขนาด: {char_count:,} chars → {chunk_count} chunks\n\n"
        f"Model: {model}\n"
        f"Genre: {genre}\n"
        f"Profile: {prof}  |  เรื่อง: {title}\n"
        f"สรรพนาม: {pronoun}\n"
        f"Custom prompt: {'ตั้งแล้ว ✓' if custom else 'ไม่ได้ตั้ง'}\n"
        f"บริบทต่อเนื่อง: {'มีจากตอนที่แล้ว ✓' if prev_ctx else 'เริ่มใหม่'}\n\n"
        f"กด Translate เพื่อเริ่มแปล"
    )


def _novel_preview_buttons(data):
    rows = [
        [InlineKeyboardButton("📖 Translate Novel", callback_data="novel:go")],
        [
            InlineKeyboardButton("🤖 Model", callback_data="novel:model"),
            InlineKeyboardButton("🎭 Genre", callback_data="novel:genre"),
        ],
        [InlineKeyboardButton(f"💬 {_pronoun_label(data)}", callback_data="novel:pronouns")],
    ]
    if data.get("titles"):
        title = data.get("current_title") or "เลือกชื่อเรื่อง..."
        rows.append([InlineKeyboardButton(f"📖 {title}", callback_data="novel:title")])
    if get_novel_context(data):
        rows.append([InlineKeyboardButton("🔄 เริ่มใหม่ (ล้าง context)", callback_data="novel:fresh")])
    return InlineKeyboardMarkup(rows)

async def handle_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle incoming photo - show settings confirmation first."""
    uid = update.effective_user.id
    data = load_user(uid)

    if not data.get("api_key"):
        await update.message.reply_text("Set API key first: /setkey <key>")
        return

    # Download and store image
    try:
        if update.message.photo:
            photo = update.message.photo[-1]
            file = await ctx.bot.get_file(photo.file_id)
        elif update.message.document:
            file = await ctx.bot.get_file(update.message.document.file_id)
        else:
            await update.message.reply_text("Send a photo or image file")
            return

        img_bytes_io = io.BytesIO()
        await file.download_to_memory(img_bytes_io)
        img_bytes_io.seek(0)

        img = Image.open(img_bytes_io)
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        img_data = buf.getvalue()
    except Exception as e:
        await update.message.reply_text(f"Error downloading: {e}")
        return

    _pending_images[uid] = img_data

    await update.message.reply_text(_settings_text(data), reply_markup=_settings_buttons(data))


async def handle_novel_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                            text_content: str, filename: str):
    """Show novel translation preview and settings before translating."""
    uid = update.effective_user.id
    data = load_user(uid)

    if not data.get("api_key"):
        await update.message.reply_text("Set API key first: /setkey <key>")
        return

    text_content = text_content.strip()
    if not text_content:
        await update.message.reply_text("ไฟล์ว่างเปล่า")
        return

    chunks = split_novel_text(text_content)
    char_count = len(text_content)
    _pending_novels[uid] = {"chunks": chunks, "filename": filename, "char_count": char_count}

    await update.message.reply_text(
        _novel_preview_text(data, filename, char_count, len(chunks)),
        reply_markup=_novel_preview_buttons(data),
    )


async def callback_novel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle novel translation callbacks."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = load_user(uid)
    action = query.data[6:]  # remove "novel:"

    # --- Stop ---
    if action == "stop":
        _stop_novel.add(uid)
        await query.answer("⏹ กำลังหยุด... รอ chunk ปัจจุบันเสร็จก่อน", show_alert=True)
        return

    # --- Model/Genre/Back (settings within novel preview) ---
    if action == "model":
        novel_data = _pending_novels.get(uid)
        if not novel_data:
            await query.edit_message_text("ไม่มีไฟล์รอแปล ส่งไฟล์ .txt มาใหม่")
            return
        current = data.get("model", DEFAULT_MODEL)
        buttons = [
            [InlineKeyboardButton(f"{'>> ' if m == current else ''}{m}", callback_data=f"nvm:{m}")]
            for m in AVAILABLE_MODELS
        ]
        buttons.append([InlineKeyboardButton("<< Back", callback_data="novel:back")])
        await query.edit_message_text("เลือก Model:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if action == "genre":
        novel_data = _pending_novels.get(uid)
        if not novel_data:
            await query.edit_message_text("ไม่มีไฟล์รอแปล ส่งไฟล์ .txt มาใหม่")
            return
        current = data.get("genre", "ไม่ระบุ (ทั่วไป)")
        buttons = [
            [InlineKeyboardButton(f"{'>> ' if g == current else ''}{g}", callback_data=f"nvg:{i}")]
            for i, g in enumerate(GENRE_LIST)
        ]
        buttons.append([InlineKeyboardButton("<< Back", callback_data="novel:back")])
        await query.edit_message_text("เลือก Genre:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if action == "title":
        novel_data = _pending_novels.get(uid)
        if not novel_data:
            await query.edit_message_text("ไม่มีไฟล์รอแปล ส่งไฟล์ .txt มาใหม่")
            return
        titles = data.get("titles", [])
        if not titles:
            await query.answer("ไม่มีชื่อเรื่อง กรุณาใช้ /addtitle ก่อน", show_alert=True)
            return
        current = data.get("current_title")
        buttons = [
            [InlineKeyboardButton(f"{'>> ' if t == current else ''}{t}", callback_data=f"nvt:{i}")]
            for i, t in enumerate(titles)
        ]
        buttons.append([InlineKeyboardButton("<< Back", callback_data="novel:back")])
        await query.edit_message_text("เลือกชื่อเรื่อง:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if action == "pronouns":
        current = get_pronoun_style(data)
        buttons = [
            [InlineKeyboardButton(f"{'>> ' if instr == current else ''}{name}",
                                  callback_data=f"nvpr:{i}")]
            for i, (name, instr) in enumerate(PRONOUN_PRESETS)
        ]
        buttons.append([InlineKeyboardButton("<< Back", callback_data="novel:back")])
        await query.edit_message_text("เลือกสรรพนาม:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if action == "back":
        novel_data = _pending_novels.get(uid)
        if not novel_data:
            await query.edit_message_text("ไม่มีไฟล์รอแปล ส่งไฟล์ .txt มาใหม่")
            return
        await query.edit_message_text(
            _novel_preview_text(data, novel_data["filename"],
                                novel_data["char_count"], len(novel_data["chunks"])),
            reply_markup=_novel_preview_buttons(data),
        )
        return

    # --- Fresh: clear context then fall through to translate ---
    if action == "fresh":
        set_novel_context(data, "")
        save_user(uid, data)

    # --- Go / Fresh → translate ---
    novel_data = _pending_novels.pop(uid, None)
    if not novel_data:
        await query.edit_message_text("ไม่มีไฟล์รอแปล กรุณาส่งไฟล์ .txt มาใหม่")
        return

    chunks = novel_data["chunks"]
    filename = novel_data["filename"]
    total = len(chunks)
    msg = query.message

    api_key = data.get("api_key", "")
    if not api_key:
        await msg.edit_text("Set API key first: /setkey <key>")
        return

    model_name = data.get("model", DEFAULT_MODEL)
    genre_ctx = GENRE_PRESETS.get(data.get("genre", "ไม่ระบุ (ทั่วไป)"), "")
    glossary = get_glossary(data)
    custom_ctx = get_custom_prompt(data)
    pronoun_ctx = get_pronoun_style(data)
    prev_context = get_novel_context(data)
    _stop_novel.discard(uid)

    stop_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⏹ Stop", callback_data="novel:stop")]])
    translated_chunks = []
    stopped = False

    try:
        for i, chunk in enumerate(chunks):
            if uid in _stop_novel:
                _stop_novel.discard(uid)
                stopped = True
                break
            await msg.edit_text(
                f"📖 กำลังแปล {i+1}/{total}  (model: {model_name})",
                reply_markup=stop_kb,
            )
            translated, gloss_section = translate_novel_chunk(
                chunk, api_key, model_name, genre_ctx, glossary,
                custom_ctx, prev_context, chunk_num=i+1, pronoun_ctx=pronoun_ctx
            )
            if gloss_section:
                glossary = parse_glossary(gloss_section, glossary)
            translated_chunks.append(translated)
            prev_context = translated[-600:] if len(translated) > 600 else translated

        set_glossary(data, glossary)
        set_novel_context(data, prev_context)
        save_user(uid, data)

        # Auto-push glossary to sheet
        auto_push_note = ""
        if SHEETS_AVAILABLE and glossary and data.get("sheet_id") and data.get("current_title"):
            creds_path = os.path.join(DATA_DIR, "credentials.json")
            if os.path.exists(creds_path):
                try:
                    count = push_glossary_to_sheet(
                        data["sheet_id"], data["current_title"], glossary,
                        creds_path, data.get("sheet_name")
                    )
                    if count > 0:
                        auto_push_note = f"\n[Sheet] บันทึก {count} คำใหม่ → {data['current_title']}"
                except Exception as push_err:
                    auto_push_note = f"\n[Sheet] Push ล้มเหลว: {push_err}"

        done_chunks = len(translated_chunks)
        combined = "\n\n---\n\n".join(translated_chunks)

        # Output filename: prefer current_title, fallback to original filename
        title_slug = data.get("current_title") or filename.rsplit(".", 1)[0]
        out_name = f"{title_slug}_TH.txt"

        stop_note = f" (หยุดที่ chunk {done_chunks}/{total})" if stopped else ""
        caption = (
            f"📖 {title_slug}\n"
            f"แปลแล้ว {done_chunks}/{total} chunks | Glossary: {len(glossary)} entries"
            f"{stop_note}{auto_push_note}"
        )

        status = f"⏹ หยุดที่ {done_chunks}/{total} chunks" if stopped else f"✅ แปลเสร็จ! {done_chunks} chunks"
        await msg.edit_text(f"{status} — กำลังส่งไฟล์...")
        await msg.reply_document(
            document=io.BytesIO(combined.encode("utf-8")),
            filename=out_name,
            caption=caption,
        )

    except Exception as e:
        logger.error(f"Novel translation error: {e}")
        await msg.edit_text(f"Error: {e}")


async def cmd_resetnovel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Clear novel rolling context for current profile."""
    uid = update.effective_user.id
    data = load_user(uid)
    if not data.get("current_profile"):
        await update.message.reply_text("เลือก profile ก่อน")
        return
    set_novel_context(data, "")
    save_user(uid, data)
    await update.message.reply_text("ล้าง novel context แล้ว — แปลตอนต่อไปจะเริ่มใหม่")


async def callback_translate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle translation flow callbacks."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = load_user(uid)
    action = query.data[3:]  # remove "tr:" prefix

    if action == "go":
        img_data = _pending_images.pop(uid, None)
        if not img_data:
            await query.edit_message_text("No image pending. Send a new image.")
            return

        await query.edit_message_text("OCR + Translating...")
        msg = query.message

        try:
            api_key = data["api_key"]
            model_name = data.get("model", DEFAULT_MODEL)
            genre_name = data.get("genre", "ไม่ระบุ (ทั่วไป)")
            genre_ctx = GENRE_PRESETS.get(genre_name, "")
            glossary = get_glossary(data)
            glossary_ctx = format_glossary_context(glossary)
            custom_ctx = get_custom_prompt(data)
            pronoun_ctx = get_pronoun_style(data)

            translated, gloss_section = translate_image_bytes(
                img_data, api_key, model_name, genre_ctx, glossary_ctx, custom_ctx, pronoun_ctx
            )

            if gloss_section:
                glossary = parse_glossary(gloss_section, glossary)
                set_glossary(data, glossary)
                save_user(uid, data)

            prof = data.get("current_profile", "")
            header = f"[{prof}] ({model_name})" if prof else f"({model_name})"
            response = f"{header}\n{translated}"

            if glossary:
                response += "\n\n[Glossary]"
                for orig, info in glossary.items():
                    response += f"\n- {orig} -> {info['translated']}: {info['description']}"

            # Auto-push new glossary entries to sheet
            auto_push_note = ""
            if SHEETS_AVAILABLE and gloss_section:
                if not data.get("sheet_id"):
                    auto_push_note = "\n\n[Sheet] ยังไม่ได้ตั้งค่า sheet → /setsheet <URL>"
                elif not data.get("current_title"):
                    auto_push_note = "\n\n[Sheet] ยังไม่ได้เลือกชื่อเรื่อง → /addtitle แล้วกดเลือกในเมนู"
                else:
                    creds_path = os.path.join(DATA_DIR, "credentials.json")
                    if not os.path.exists(creds_path):
                        auto_push_note = "\n\n[Sheet] ไม่พบ credentials.json → ตั้ง env var GOOGLE_CREDENTIALS_JSON"
                    else:
                        try:
                            count = push_glossary_to_sheet(
                                data["sheet_id"], data["current_title"], glossary,
                                creds_path, data.get("sheet_name")
                            )
                            if count > 0:
                                auto_push_note = f"\n\n[Sheet] บันทึก {count} คำใหม่ → {data['current_title']}"
                        except Exception as push_err:
                            logger.error(f"Auto-push error: {push_err}")
                            auto_push_note = f"\n\n[Sheet] Push ล้มเหลว: {push_err}"

            response += auto_push_note

            if len(response) <= 4096:
                await msg.edit_text(response)
            else:
                await msg.edit_text(response[:4096])
                for i in range(4096, len(response), 4096):
                    await msg.reply_text(response[i:i+4096])

        except Exception as e:
            logger.error(f"Translation error: {e}")
            await msg.edit_text(f"Error: {str(e)}")

    elif action == "model":
        # Show model selection
        current = data.get("model", DEFAULT_MODEL)
        buttons = []
        for m in AVAILABLE_MODELS:
            label = f"{'>> ' if m == current else ''}{m}"
            buttons.append([InlineKeyboardButton(label, callback_data=f"trm:{m}")])
        buttons.append([InlineKeyboardButton("<< Back", callback_data="tr:back")])
        await query.edit_message_text("Select model:", reply_markup=InlineKeyboardMarkup(buttons))

    elif action == "genre":
        # Show genre selection
        current = data.get("genre", "ไม่ระบุ (ทั่วไป)")
        buttons = []
        for i, g in enumerate(GENRE_LIST):
            label = f"{'>> ' if g == current else ''}{g}"
            buttons.append([InlineKeyboardButton(label, callback_data=f"trg:{i}")])
        buttons.append([InlineKeyboardButton("<< Back", callback_data="tr:back")])
        await query.edit_message_text("Select genre:", reply_markup=InlineKeyboardMarkup(buttons))

    elif action == "title":
        titles = data.get("titles", [])
        if not titles:
            await query.answer("ไม่มีชื่อเรื่อง กรุณาใช้ /addtitle ก่อน", show_alert=True)
            return
        current = data.get("current_title")
        buttons = []
        for i, t in enumerate(titles):
            mark = " ◀" if t == current else ""
            buttons.append([InlineKeyboardButton(f"{t}{mark}", callback_data=f"trt:{i}")])
        buttons.append([InlineKeyboardButton("<< Back", callback_data="tr:back")])
        await query.edit_message_text("เลือกชื่อเรื่องที่จะแปล:", reply_markup=InlineKeyboardMarkup(buttons))

    elif action == "prompt":
        prof = data.get("current_profile")
        if not prof:
            await query.answer("เลือก profile ก่อน", show_alert=True)
            return
        custom = get_custom_prompt(data)
        text = f"Custom prompt [{prof}]:\n\n"
        if custom:
            text += f'"{custom}"\n\nใช้ /setprompt <text> เพื่อเปลี่ยน'
        else:
            text += "ยังไม่ได้ตั้ง\n\nใช้ /setprompt <text> เพื่อตั้ง\nเช่น:\n/setprompt ใช้สรรพนาม ข้า/ท่าน ตลอด"
        buttons = []
        if custom:
            buttons.append([InlineKeyboardButton("ลบ prompt", callback_data="tr:clearprompt")])
        buttons.append([InlineKeyboardButton("<< Back", callback_data="tr:back")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    elif action == "clearprompt":
        set_custom_prompt(data, "")
        save_user(uid, data)
        await query.edit_message_text(_settings_text(data), reply_markup=_settings_buttons(data))

    elif action == "pronouns":
        if not data.get("current_profile"):
            await query.answer("เลือก profile ก่อน", show_alert=True)
            return
        current = get_pronoun_style(data)
        buttons = [
            [InlineKeyboardButton(f"{'>> ' if instr == current else ''}{name}",
                                  callback_data=f"trpr:{i}")]
            for i, (name, instr) in enumerate(PRONOUN_PRESETS)
        ]
        buttons.append([InlineKeyboardButton("<< Back", callback_data="tr:back")])
        await query.edit_message_text("เลือกสรรพนาม:", reply_markup=InlineKeyboardMarkup(buttons))

    elif action == "back":
        await query.edit_message_text(_settings_text(data), reply_markup=_settings_buttons(data))


async def callback_trmodel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle model selection during translate flow."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    model_name = query.data[4:]  # remove "trm:"
    data = load_user(uid)
    data["model"] = model_name
    save_user(uid, data)
    await query.edit_message_text(_settings_text(data), reply_markup=_settings_buttons(data))


async def callback_trgenre(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle genre selection during translate flow."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    idx = int(query.data[4:])  # remove "trg:"
    data = load_user(uid)
    data["genre"] = GENRE_LIST[idx]
    prof = data.get("current_profile")
    if prof and prof in data.get("profiles", {}):
        data["profiles"][prof]["genre"] = GENRE_LIST[idx]
    save_user(uid, data)
    await query.edit_message_text(_settings_text(data), reply_markup=_settings_buttons(data))


async def callback_trtitle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle title selection during translate flow."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    idx = int(query.data[4:])  # remove "trt:"
    data = load_user(uid)
    titles = data.get("titles", [])
    if idx < len(titles):
        data["current_title"] = titles[idx]
        save_user(uid, data)
    await query.edit_message_text(_settings_text(data), reply_markup=_settings_buttons(data))


async def callback_trpronoun(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle pronoun preset selection during image translate flow."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    idx = int(query.data[5:])  # remove "trpr:"
    data = load_user(uid)
    _, instruction = PRONOUN_PRESETS[idx]
    set_pronoun_style(data, instruction)
    save_user(uid, data)
    await query.edit_message_text(_settings_text(data), reply_markup=_settings_buttons(data))


async def callback_nvmodel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle model selection during novel translate flow."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    model_name = query.data[4:]  # remove "nvm:"
    data = load_user(uid)
    data["model"] = model_name
    save_user(uid, data)
    novel_data = _pending_novels.get(uid)
    if novel_data:
        await query.edit_message_text(
            _novel_preview_text(data, novel_data["filename"],
                                novel_data["char_count"], len(novel_data["chunks"])),
            reply_markup=_novel_preview_buttons(data),
        )
    else:
        await query.edit_message_text(f"Model set to: {model_name}\nส่งไฟล์ .txt มาใหม่เพื่อแปล")


async def callback_nvgenre(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle genre selection during novel translate flow."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    idx = int(query.data[4:])  # remove "nvg:"
    data = load_user(uid)
    data["genre"] = GENRE_LIST[idx]
    prof = data.get("current_profile")
    if prof and prof in data.get("profiles", {}):
        data["profiles"][prof]["genre"] = GENRE_LIST[idx]
    save_user(uid, data)
    novel_data = _pending_novels.get(uid)
    if novel_data:
        await query.edit_message_text(
            _novel_preview_text(data, novel_data["filename"],
                                novel_data["char_count"], len(novel_data["chunks"])),
            reply_markup=_novel_preview_buttons(data),
        )
    else:
        await query.edit_message_text(f"Genre set to: {GENRE_LIST[idx]}\nส่งไฟล์ .txt มาใหม่เพื่อแปล")


async def callback_nvtitle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle title selection during novel translate flow."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    idx = int(query.data[4:])  # remove "nvt:"
    data = load_user(uid)
    titles = data.get("titles", [])
    if idx < len(titles):
        data["current_title"] = titles[idx]
        save_user(uid, data)
    novel_data = _pending_novels.get(uid)
    if novel_data:
        await query.edit_message_text(
            _novel_preview_text(data, novel_data["filename"],
                                novel_data["char_count"], len(novel_data["chunks"])),
            reply_markup=_novel_preview_buttons(data),
        )
    else:
        await query.edit_message_text(f"เลือกเรื่อง: {data.get('current_title')}\nส่งไฟล์ .txt มาใหม่เพื่อแปล")


async def callback_nvpronoun(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle pronoun preset selection during novel translate flow."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    idx = int(query.data[5:])  # remove "nvpr:"
    data = load_user(uid)
    _, instruction = PRONOUN_PRESETS[idx]
    set_pronoun_style(data, instruction)
    save_user(uid, data)
    novel_data = _pending_novels.get(uid)
    if novel_data:
        await query.edit_message_text(
            _novel_preview_text(data, novel_data["filename"],
                                novel_data["char_count"], len(novel_data["chunks"])),
            reply_markup=_novel_preview_buttons(data),
        )
    else:
        await query.edit_message_text(f"สรรพนาม: {_pronoun_label(data)}\nส่งไฟล์ .txt มาใหม่เพื่อแปล")


async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle ZIP or image files."""
    uid = update.effective_user.id
    data = load_user(uid)

    if not data.get("api_key"):
        await update.message.reply_text("Set API key first: /setkey <key>")
        return

    doc = update.message.document
    fname = doc.file_name or ""

    # Check if image
    if fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
        await handle_image(update, ctx)
        return

    # Check if text file (novel)
    if fname.lower().endswith(".txt"):
        file = await ctx.bot.get_file(doc.file_id)
        buf = io.BytesIO()
        await file.download_to_memory(buf)
        buf.seek(0)
        text_content = buf.read().decode("utf-8", errors="replace")
        await handle_novel_file(update, ctx, text_content, fname)
        return

    # Check if ZIP
    if not fname.lower().endswith(".zip"):
        await update.message.reply_text("Send an image (PNG/JPG) or ZIP file")
        return

    msg = await update.message.reply_text("Downloading ZIP...")

    try:
        file = await ctx.bot.get_file(doc.file_id)
        zip_bytes = io.BytesIO()
        await file.download_to_memory(zip_bytes)
        zip_bytes.seek(0)

        images = []
        with zipfile.ZipFile(zip_bytes, 'r') as zf:
            for name in sorted(zf.namelist()):
                if name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                    img_data = zf.read(name)
                    img = Image.open(io.BytesIO(img_data))
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG")
                    images.append((os.path.basename(name), buf.getvalue()))

        if not images:
            await msg.edit_text("No images found in ZIP")
            return

        total = len(images)
        await msg.edit_text(f"Found {total} images. Translating...")

        api_key = data["api_key"]
        model_name = data.get("model", DEFAULT_MODEL)
        genre_name = data.get("genre", "ไม่ระบุ (ทั่วไป)")
        genre_ctx = GENRE_PRESETS.get(genre_name, "")
        glossary = get_glossary(data)
        custom_ctx = get_custom_prompt(data)
        pronoun_ctx = get_pronoun_style(data)

        all_pages = []
        for i, (fname, img_data) in enumerate(images):
            page_num = i + 1
            await msg.edit_text(f"Translating {page_num}/{total}: {fname}...")

            glossary_ctx = format_glossary_context(glossary)
            translated, gloss_section = translate_image_bytes(
                img_data, api_key, model_name, genre_ctx, glossary_ctx, custom_ctx, pronoun_ctx
            )

            if gloss_section:
                glossary = parse_glossary(gloss_section, glossary)

            page_text = f"Page {page_num:02d}\n\n{translated}"
            all_pages.append(page_text)

        set_glossary(data, glossary)
        save_user(uid, data)

        # Auto-push new glossary entries to sheet
        auto_push_note = ""
        if SHEETS_AVAILABLE and glossary:
            if not data.get("sheet_id"):
                auto_push_note = "\n[Sheet] ยังไม่ได้ตั้งค่า sheet → /setsheet <URL>"
            elif not data.get("current_title"):
                auto_push_note = "\n[Sheet] ยังไม่ได้เลือกชื่อเรื่อง → /addtitle แล้วกดเลือกในเมนู"
            else:
                creds_path = os.path.join(DATA_DIR, "credentials.json")
                if not os.path.exists(creds_path):
                    auto_push_note = "\n[Sheet] ไม่พบ credentials.json → ตั้ง env var GOOGLE_CREDENTIALS_JSON"
                else:
                    try:
                        count = push_glossary_to_sheet(
                            data["sheet_id"], data["current_title"], glossary,
                            creds_path, data.get("sheet_name")
                        )
                        if count > 0:
                            auto_push_note = f"\n[Sheet] บันทึก {count} คำใหม่ → {data['current_title']}"
                    except Exception as push_err:
                        logger.error(f"Auto-push error: {push_err}")
                        auto_push_note = f"\n[Sheet] Push ล้มเหลว: {push_err}"

        combined = "\n\n".join(all_pages)
        if glossary:
            combined += "\n\n[Glossary]"
            for orig, info in glossary.items():
                combined += f"\n- {orig} -> {info['translated']}: {info['description']}"

        if len(combined) > 4096:
            txt_bytes = combined.encode("utf-8")
            zip_name = doc.file_name.replace(".zip", ".txt") if doc.file_name else "translated.txt"
            caption = f"Translated {total} pages | Glossary: {len(glossary)} entries{auto_push_note}"
            await msg.edit_text(f"Done\! {total} pages translated. Sending file...")
            await update.message.reply_document(
                document=io.BytesIO(txt_bytes),
                filename=zip_name,
                caption=caption,
            )
        else:
            await msg.edit_text(combined + auto_push_note)

    except Exception as e:
        logger.error(f"ZIP error: {e}")
        await msg.edit_text(f"Error: {str(e)}")


# ============================================================
# MAIN
# ============================================================
def main():
    token = BOT_TOKEN
    if not token:
        cfg_path = os.path.join(DATA_DIR, "bot_token.txt")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r") as f:
                token = f.read().strip()

    if not token and sys.stdin.isatty():
        print("="*50)
        print("  Manhwa Translator - Telegram Bot")
        print("="*50)
        print()
        token = input("Enter Telegram Bot Token: ").strip()
        if token:
            cfg_path = os.path.join(DATA_DIR, "bot_token.txt")
            with open(cfg_path, "w") as f:
                f.write(token)
            print(f"Token saved to {cfg_path}")

    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN environment variable is not set.")
        sys.exit(1)

    # Write credentials.json from env var (always overwrite so changes take effect)
    creds_env = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    if creds_env:
        creds_path = os.path.join(DATA_DIR, "credentials.json")
        with open(creds_path, "w", encoding="utf-8") as f:
            f.write(creds_env)
        logger.info("credentials.json written from GOOGLE_CREDENTIALS_JSON env var")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("setkey", cmd_setkey))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("profiles", cmd_profiles))
    app.add_handler(CommandHandler("newprofile", cmd_newprofile))
    app.add_handler(CommandHandler("select", cmd_select))
    app.add_handler(CommandHandler("delprofile", cmd_delprofile))
    app.add_handler(CommandHandler("genre", cmd_genre))
    app.add_handler(CommandHandler("setgenre", cmd_setgenre))
    app.add_handler(CommandHandler("glossary", cmd_glossary))
    app.add_handler(CommandHandler("clearglossary", cmd_clearglossary))
    app.add_handler(CommandHandler("save", cmd_save))
    app.add_handler(CommandHandler("setsheet", cmd_setsheet))
    app.add_handler(CommandHandler("sync", cmd_sync))
    app.add_handler(CommandHandler("pushsheet", cmd_pushsheet))
    app.add_handler(CommandHandler("setsheetname", cmd_setsheetname))
    app.add_handler(CommandHandler("addtitle", cmd_addtitle))
    app.add_handler(CommandHandler("titles", cmd_titles))
    app.add_handler(CommandHandler("deltitle", cmd_deltitle))
    app.add_handler(CommandHandler("setprompt", cmd_setprompt))
    app.add_handler(CommandHandler("prompt", cmd_prompt))
    app.add_handler(CommandHandler("clearprompt", cmd_clearprompt))
    app.add_handler(CommandHandler("resetnovel", cmd_resetnovel))
    app.add_handler(CallbackQueryHandler(callback_novel, pattern="^novel:"))
    app.add_handler(CallbackQueryHandler(callback_nvmodel, pattern="^nvm:"))
    app.add_handler(CallbackQueryHandler(callback_nvgenre, pattern="^nvg:"))
    app.add_handler(CallbackQueryHandler(callback_nvtitle, pattern="^nvt:"))
    app.add_handler(CallbackQueryHandler(callback_nvpronoun, pattern="^nvpr:"))
    app.add_handler(CallbackQueryHandler(callback_model, pattern="^model:"))
    app.add_handler(CallbackQueryHandler(callback_translate, pattern="^tr:"))
    app.add_handler(CallbackQueryHandler(callback_trmodel, pattern="^trm:"))
    app.add_handler(CallbackQueryHandler(callback_trgenre, pattern="^trg:"))
    app.add_handler(CallbackQueryHandler(callback_trtitle, pattern="^trt:"))
    app.add_handler(CallbackQueryHandler(callback_trpronoun, pattern="^trpr:"))
    app.add_handler(CallbackQueryHandler(callback_tts, pattern="^tts:"))

    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("Bot is running\! Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
