import time
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.models import FlexSendMessage, TextSendMessage, QuickReply, QuickReplyButton, MessageAction
import json
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer, util

# ตั้งค่า Flask app
app = Flask(__name__)

# Replace with your actual LineBotApi and WebhookHandler keys
line_bot_api = LineBotApi('UnWI5iWcYhUSfMPIIXxjXIPb39+L7+szaa5099nc1TKhttvnUa8S02TK9kLjy439BUAwC4g9txMYrcvHrm8VmDgAAgZfYFMJjpHPOl2hUQJqzVha9cZQLgM+cYBUjMEFW3Bw4+geTdi+Z4qZUJJ9dQdB04t89/1O/w1cDnyilFU=')  # Replace with your actual token
handler = WebhookHandler('Y6279f9a714dfe3510ea8ddd2dc7ac7a7')  # Replace with your actual secret


# การตั้งค่า Neo4j
URI = "neo4j://localhost:7687"
AUTH = ("neo4j", "password")

# ฟังก์ชันเชื่อมต่อและรัน Query กับ Neo4j
def run_query(query, parameters=None):
    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        with driver.session() as session:
            result = session.run(query, parameters)
            return [record for record in result]

# ฟังก์ชันบันทึกประวัติการสนทนาลง Neo4j
def save_chat_history(user_id, message, reply):
    cypher_query = '''
    MERGE (u:User {id: $user_id})
    CREATE (m:Message {text: $message, timestamp: timestamp()})
    CREATE (u)-[:SENT]->(m)
    CREATE (r:Reply {text: $reply, timestamp: timestamp()})
    CREATE (m)-[:HAS_REPLY]->(r)
    '''
    run_query(cypher_query, {"user_id": user_id, "message": message, "reply": reply})

# ตั้งค่าโมเดล SentenceTransformer
model = SentenceTransformer('sentence-transformers/distiluse-base-multilingual-cased-v2')

# ดึงข้อมูลข้อความจาก Neo4j
def load_greeting_corpus():
    cypher_query = '''
    MATCH (n:Greeting) RETURN n.name as name, n.msg_reply as reply;
    '''
    greeting_corpus = []
    results = run_query(cypher_query)
    for record in results:
        greeting_corpus.append(record['name'])
    return list(set(greeting_corpus))  # เอาข้อความมาใส่ใน corpus

greeting_corpus = load_greeting_corpus()
greeting_vec = model.encode(greeting_corpus, convert_to_tensor=True, normalize_embeddings=True)

# Quick Reply URL Mapping สำหรับหมวดหมู่หลัก
quick_reply_url_map = {
    "จานเดี่ยว": "https://www.mk1642.com/th/Product/SingleDish.aspx",
    "ชุดสุดคุ้ม": "https://www.mk1642.com/th/Product/SetMeal.aspx",
    "สุกี้สด": "https://www.mk1642.com/th/Product/FreshSuki.aspx",
    "เป็ดย่างและอื่นๆ": "https://www.mk1642.com/th/Product/Roasted.aspx",
    "ของทานเล่น": "https://www.mk1642.com/th/Product/Snack.aspx",
    "น้ำและขนม": "https://www.mk1642.com/th/Product/Dessert.aspx"
}

# เพิ่ม Quick Reply ย่อยสำหรับแต่ละหมวดหมู่
quick_reply_subcategory_map = {
    "จานเดี่ยว": {
        "ข้าว": "https://www.mk1642.com/th/Product/SingleDish.aspx?type=7&searchtext=",
        "บะหมี่": "https://www.mk1642.com/th/Product/SingleDish.aspx?type=8&searchtext=",
        "สุกี้": "https://www.mk1642.com/th/Product/SingleDish.aspx?type=9&searchtext=",
        "เกี๊ยว": "https://www.mk1642.com/th/Product/SingleDish.aspx?type=10&searchtext="
    },
    "ชุดสุดคุ้ม": {
        "1 ท่าน": "https://www.mk1642.com/th/Product/SetMeal.aspx?type=11&searchtext=",
        "เซ็ตข้าว": "https://www.mk1642.com/th/Product/SetMeal.aspx?type=14&searchtext=",
        "เซ็ตบะหมี่": "https://www.mk1642.com/th/Product/SetMeal.aspx?type=15&searchtext="
    },
    "สุกี้สด": {
        "เซ็ตสุกี้": "https://www.mk1642.com/th/Product/FreshSuki.aspx?type=21&searchtext=",
        "คอนโด": "https://www.mk1642.com/th/Product/FreshSuki.aspx?type=22&searchtext=",
        "เนื้อสัตว์": "https://www.mk1642.com/th/Product/FreshSuki.aspx?type=23&searchtext=",
        "ลูกชิ้น": "https://www.mk1642.com/th/Product/FreshSuki.aspx?type=24&searchtext=",
        "ผักและอื่นๆ": "https://www.mk1642.com/th/Product/FreshSuki.aspx?type=24&searchtext="
    },
    "เป็ดย่างและอื่นๆ": {
        "เป็ด": "https://www.mk1642.com/th/Product/Roasted.aspx?type=16&searchtext=",
        "หมู": "https://www.mk1642.com/th/Product/Roasted.aspx?type=17&searchtext=",
        "ผัก": "https://www.mk1642.com/th/Product/Roasted.aspx?type=19&searchtext=",
        "บะหมี่หยก": "https://www.mk1642.com/th/Product/Roasted.aspx?type=20&searchtext="
    },
    "ของทานเล่น": {
        "นึ่ง": "https://www.mk1642.com/th/Product/Snack.aspx?type=26&searchtext=",
        "ทอด": "https://www.mk1642.com/th/Product/Snack.aspx?type=27&searchtext=",
        "อื่นๆ": "https://www.mk1642.com/th/Product/Snack.aspx?type=28&searchtext="
    },
    "น้ำและขนม": {
        "น้ำ": "https://www.mk1642.com/th/Product/Dessert.aspx?type=29&searchtext=",
        "ขนม": "https://www.mk1642.com/th/Product/Dessert.aspx?type=30&searchtext="
    }
}

# ฟังก์ชันส่ง Quick Reply หลังจากการทักทาย
def send_greeting_and_quick_reply(reply_token, greeting_msg):
    text_message = TextSendMessage(text=greeting_msg)
    quick_reply_message = TextSendMessage(
        text="หากไม่เป็นการรบกวน ท่านสามารถเลือกหมวดหมู่อาหารที่ต้องการดูได้เลยครับ..",
        quick_reply=QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="จานเดี่ยว", text="จานเดี่ยว")),
            QuickReplyButton(action=MessageAction(label="ชุดสุดคุ้ม", text="ชุดสุดคุ้ม")),
            QuickReplyButton(action=MessageAction(label="สุกี้สด", text="สุกี้สด")),
            QuickReplyButton(action=MessageAction(label="เป็ดย่างและอื่นๆ", text="เป็ดย่างและอื่นๆ")),
            QuickReplyButton(action=MessageAction(label="ของทานเล่น", text="ของทานเล่น")),
            QuickReplyButton(action=MessageAction(label="น้ำและขนม", text="น้ำและขนม"))
        ])
    )
    line_bot_api.reply_message(reply_token, [text_message, quick_reply_message])

# ฟังก์ชันส่ง Quick Reply ย่อย
def send_subcategory_quick_reply(reply_token, category):
    if category in quick_reply_subcategory_map:
        subcategories = quick_reply_subcategory_map[category]
        quick_reply_items = [QuickReplyButton(action=MessageAction(label=sub_cat, text=sub_cat)) for sub_cat in subcategories.keys()]
        
        quick_reply_message = TextSendMessage(
            text=f"กรุณาเลือกหมวดย่อยของ {category}:",
            quick_reply=QuickReply(items=quick_reply_items)
        )
        
        line_bot_api.reply_message(reply_token, [quick_reply_message])

# ฟังก์ชันสแครปรายละเอียดข้อมูลอาหาร
def scrape_mk_suki(url, retries=3, delay=5):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
    }
    
    for i in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            print(f"เกิดข้อผิดพลาดในการเชื่อมต่อ: {e}, retrying... ({i+1}/{retries})")
            if i < retries - 1:
                time.sleep(delay)
            else:
                return []

    soup = BeautifulSoup(response.text, 'html.parser')

    promotion_elements = soup.find_all("div", {"class": "col-6 col-lg-4 cmn-t-translate-bshadow product-card-padding card-template"})
    result = []
    for promotion in promotion_elements:
        a_tag = promotion.find("a", href=True)
        if not a_tag:
            continue

        title = a_tag.get('data-name', 'No title')
        price_str = a_tag.get('data-price', 'No price')
        price = float(price_str.replace('฿', '').replace(',', '').strip()) if price_str != 'No price' else 0.0  # แปลงราคาให้เป็นตัวเลข
        link = a_tag['href']
        full_link = f"https://www.mk1642.com{link}" if link.startswith("/") else link

        image_element = promotion.find("img")
        image_src = image_element.get("data-src") or image_element.get("src") if image_element else "No image"
        image_url = f"https://www.mk1642.com{image_src}" if not image_src.startswith("http") else image_src

        result.append({
            'title': title,
            'price': price,
            'image_url': image_url,
            'link': full_link
        })

    # เรียงลำดับตามราคา (น้อยไปมาก)
    result = sorted(result, key=lambda x: x['price'])

    return result

# ฟังก์ชันส่ง Flex Message กับรายละเอียดอาหาร
def send_flex_message(reply_token, promotions):
    if not promotions:
        text_message = TextSendMessage(text="ไม่พบข้อมูลในขณะนี้.")
        line_bot_api.reply_message(reply_token, [text_message])
        return

    bubbles = [{
        "type": "bubble",
        "hero": {
            "type": "image",
            "url": promo['image_url'],
            "size": "full",
            "aspectRatio": "4:3",
            "aspectMode": "cover"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": promo['title'], "weight": "bold", "size": "lg", "wrap": True},
                {"type": "text", "text": f"ราคา: ฿{promo['price']:.2f}", "size": "xl", "color": "#FF4500", "weight": "bold"}  # แสดงราคา
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "button", "action": {"type": "uri", "label": "ดูเพิ่มเติม", "uri": promo['link']}, "style": "primary"}
            ]
        }
    } for promo in promotions[:12]]  # จำกัดการแสดง 12 รายการแรกที่ถูกเรียงลำดับแล้ว

    contents = {"type": "carousel", "contents": bubbles}
    flex_message = FlexSendMessage(alt_text="MK Suki Promotions", contents=contents)
    line_bot_api.reply_message(reply_token, [flex_message])

# ฟังก์ชันประมวลผลการเลือกของผู้ใช้
def process_selection(reply_token, user_selection, user_id):
    if user_selection in quick_reply_url_map:
        send_subcategory_quick_reply(reply_token, user_selection)
    elif any(user_selection in subcategories for subcategories in quick_reply_subcategory_map.values()):
        for category, subcategories in quick_reply_subcategory_map.items():
            if user_selection in subcategories:
                url = subcategories.get(user_selection)
                print(f"URL สำหรับ {user_selection}: {url}")
                if url:
                    promotions = scrape_mk_suki(url)
                    send_flex_message(reply_token, promotions)

                    # บันทึกประวัติการสนทนา
                    save_chat_history(user_id, user_selection, "รายละเอียดสินค้าที่ส่งไป")
                else:
                    line_bot_api.reply_message(reply_token, TextSendMessage(text="ไม่พบหมวดหมู่นี้"))
                break
    else:
        compute_response_and_send_quick_reply(user_selection, reply_token, user_id)

# ฟังก์ชันคำนวณความคล้ายและส่ง Quick Reply
def compute_response_and_send_quick_reply(sentence, reply_token, user_id):
    ask_vec = model.encode([sentence], convert_to_tensor=True, normalize_embeddings=True)
    similarities = util.cos_sim(greeting_vec, ask_vec)
    max_score = similarities.max().item()
    max_idx = similarities.argmax().item()
    match_greeting = greeting_corpus[max_idx]

    if max_score > 0.5:
        My_cypher = f"MATCH (n:Greeting) WHERE n.name = $name RETURN n.msg_reply AS reply"
        results = run_query(My_cypher, {"name": match_greeting})
        if results:
            response_msg = results[0]['reply']
            send_greeting_and_quick_reply(reply_token, response_msg)

            # บันทึกการสนทนาลงใน Neo4j
            save_chat_history(user_id, sentence, response_msg)
            return

    response_msg = "ขอโทษ ฉันไม่เข้าใจคำถามของคุณ"
    text_message = TextSendMessage(text=response_msg)
    line_bot_api.reply_message(reply_token, [text_message])

    # บันทึกการสนทนาลงใน Neo4j
    save_chat_history(user_id, sentence, response_msg)

# LINE webhook handler
@app.route("/", methods=['POST'])
def linebot():
    body = request.get_data(as_text=True)
    try:
        json_data = json.loads(body)
        events = json_data.get('events', [])
        for event in events:
            reply_token = event.get('replyToken')
            user_id = event['source']['userId']  # ดึง User ID
            message = event.get('message', {}).get('text', '').strip()

            if not reply_token:
                continue

            if message in quick_reply_url_map or any(message in subcats for subcats in quick_reply_subcategory_map.values()):
                process_selection(reply_token, message, user_id)
            else:
                compute_response_and_send_quick_reply(message, reply_token, user_id)

    except Exception as e:
        print(f"Error processing the LINE event: {e}")

    return 'OK'

if __name__ == '__main__':
    app.run(port=5000, debug=True)
