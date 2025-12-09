import streamlit as st
import google.generativeai as genai
from PIL import Image
import json
import re

# ==========================================
# 1. AYARLAR & HAFIZA
# ==========================================
st.set_page_config(page_title="AI Sınav Asistanı v3.8", layout="wide")

# DOĞRU OLAN (Yeni halin):
import streamlit as st

# Anahtarı Streamlit'in gizli kasasından çek
genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

# Hafıza Ayarları
if 'yuklenen_resimler_v3' not in st.session_state:
    st.session_state.yuklenen_resimler_v3 = []

# Yükleyici Anahtarları (Sıfırlama için)
if 'cam_key' not in st.session_state: st.session_state.cam_key = 0
if 'file_key' not in st.session_state: st.session_state.file_key = 0


def reset_cam():
    st.session_state.cam_key += 1


def reset_file():
    st.session_state.file_key += 1


def listeyi_temizle():
    st.session_state.yuklenen_resimler_v3 = []
    st.session_state.cam_key += 1
    st.session_state.file_key += 1
    st.rerun()


# JSON Temizleme
def extract_json(text):
    text = text.strip()
    try:
        if "```json" in text: text = text.split("```json")[1].split("```")[0]
        elif "```" in text: text = text.split("```")[1].split("```")[0]
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end != 0: return text[start:end]
        return text
    except:
        return text


# ==========================================
# 2. ARAYÜZ
# ==========================================
st.title("🧠 AI Yazılı Oku (Sinan S. v3.8)")
st.markdown("---")

col_sol, col_sag = st.columns([1, 1], gap="large")

# --- SOL SÜTUN: KRİTERLER ---
with col_sol:
    st.header("1. Kriterler")
    ogretmen_promptu = st.text_area(
        "Öğretmen Notu:",
        height=100,
        placeholder=
        "Örn: Değerlendirme yaparken yapay zekanın dikkat etmesini istedikleriniz varsa yazınız."
    )

    with st.expander("Cevap Anahtarı Yükle (İsteğe Bağlı)"):
        rubrik_dosyasi = st.file_uploader("Fotoğraf Seç",
                                          type=["jpg", "png", "jpeg"],
                                          key="rubrik_up")
        rubrik_img = Image.open(rubrik_dosyasi) if rubrik_dosyasi else None
        if rubrik_img: st.image(rubrik_img, width=200)

# --- SAĞ SÜTUN: ÖĞRENCİ KAĞIDI ---
with col_sag:
    st.subheader("2. Öğrenci Kağıdı")

    # KULLANIM MODU SEÇİMİ
    mod = st.radio(
        "Çalışma Modunu Seçin:",
        ["📂 Dosya Yükle (PC / Galeri)", "📸 Canlı Kamera (Sadece Mobil)"],
        horizontal=True)

    st.markdown("---")

    # MOD A: DOSYA YÜKLEME (PC İÇİN GÜVENLİ)
    if "Dosya" in mod:
        st.info(
            "Bilgisayardan dosya seçmek veya mobilde galeri/kamera uygulamasını açmak için:"
        )
        uploaded_file = st.file_uploader(
            "Dosya Seç / Fotoğraf Çek",
            type=["jpg", "png", "jpeg"],
            key=f"file_{st.session_state.file_key}")
        if uploaded_file:
            img = Image.open(uploaded_file)
            st.session_state.yuklenen_resimler_v3.append(img)
            reset_file()  # Yükleyiciyi temizle
            st.rerun()

    # MOD B: CANLI KAMERA (MOBİL İÇİN HIZLI)
    else:
        st.warning("Kamera izni ister. PC'de web kamerasını açar.")
        cam_img = st.camera_input("Fotoğrafı Çek",
                                  key=f"cam_{st.session_state.cam_key}")
        if cam_img:
            img = Image.open(cam_img)
            st.session_state.yuklenen_resimler_v3.append(img)
            reset_cam()  # Kamerayı temizle
            st.rerun()

    # --- HAVUZ (YÜKLENENLER) ---
    if len(st.session_state.yuklenen_resimler_v3) > 0:
        st.success(
            f"📎 Toplam **{len(st.session_state.yuklenen_resimler_v3)} sayfa** hafızada."
        )

        # Yan yana küçük önizleme
        cols = st.columns(4)
        for i, img in enumerate(st.session_state.yuklenen_resimler_v3):
            with cols[i % 4]:
                st.image(img, use_container_width=True, caption=f"Sayfa {i+1}")

        if st.button("🗑️ HEPSİNİ SİL (Yeni Öğrenci)",
                     use_container_width=True,
                     type="secondary"):
            listeyi_temizle()

# ==========================================
# 3. İŞLEM
# ==========================================
st.markdown("---")

if st.button("✅ KAĞIDI OKU VE DEĞERLENDİR",
             type="primary",
             use_container_width=True):
    if not SABIT_API_KEY or "API_ANAHTARINI" in SABIT_API_KEY:
        st.error("API Anahtarı eksik!")
    elif len(st.session_state.yuklenen_resimler_v3) == 0:
        st.warning("Lütfen önce kağıt yükleyin.")
    else:
        with st.spinner("Yapay zeka analiz yapıyor..."):
            try:
                genai.configure(api_key=SABIT_API_KEY)
                model = genai.GenerativeModel("gemini-2.5-flash")

                # --- GÜÇLÜ PROMPT ---
                base_prompt = """
                Rol: Deneyimli Türk Öğretmeni.
                Görev: Öğrenci kağıdını analiz et.

                ADIM 1: KİMLİK
                - Kağıdın en üstünden İsim, Sınıf, Numara bul. Bulamazsan "-" yaz.

                ADIM 2: PUANLAMA
                - Sorudaki tüm alt maddeleri kontrol et.
                - 4 madde istenip 4'ü yazıldıysa TAM PUAN ver (ekstra yazılanlar hata değildir).
                - Sadece eksik varsa puan kır.

                ÇIKTI (JSON):
                {
                  "kimlik": { "ad_soyad": "...", "sinif": "...", "numara": "..." },
                  "degerlendirme": [
                    {
                      "no": "1",
                      "soru": "Soru özeti",
                      "cevap": "Öğrenci cevabı",
                      "puan": 10,
                      "tam_puan": 20,
                      "yorum": "Değerlendirme"
                    }
                  ]
                }
                """

                prompt_parts = [base_prompt]
                if ogretmen_promptu:
                    prompt_parts.append(f"ÖĞRETMEN NOTU: {ogretmen_promptu}")
                if rubrik_img:
                    prompt_parts.append("CEVAP ANAHTARI:")
                    prompt_parts.append(rubrik_img)

                prompt_parts.append("ÖĞRENCİ KAĞITLARI:")
                for img in st.session_state.yuklenen_resimler_v3:
                    prompt_parts.append(img)

                response = model.generate_content(prompt_parts)
                json_text = extract_json(response.text)
                data = json.loads(json_text)

                kimlik = data.get("kimlik", {})
                sorular = data.get("degerlendirme", [])

                st.balloons()

                # Puan Hesapla
                toplam = sum([float(x.get('puan', 0)) for x in sorular])
                max_toplam = sum(
                    [float(x.get('tam_puan', 0)) for x in sorular])

                # ÜST KART
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("👤 Öğrenci", kimlik.get("ad_soyad", "-"))
                    c2.metric("🏫 Sınıf", kimlik.get("sinif", "-"))
                    c3.metric("🔢 No", kimlik.get("numara", "-"))
                    # Düzeltilen Satır (Tırnak hatası giderildi)
                    c4.markdown(
                        f"<h1 style='color:#28a745; margin:0;'>{int(toplam)} / {int(max_toplam)}</h1>",
                        unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)

                # SORULAR
                for soru in sorular:
                    p = soru.get('puan', 0)
                    tp = soru.get('tam_puan', 0)
                    if tp > 0 and (p / tp) >= 0.8: renk, ikon = "green", "✅"
                    elif p == 0: renk, ikon = "red", "❌"
                    else: renk, ikon = "orange", "⚠️"

                    with st.container(border=True):
                        c1, c2 = st.columns([9, 1])
                        c1.markdown(
                            f"#### {ikon} Soru {soru.get('no')}: {soru.get('soru')}"
                        )
                        c2.markdown(f"### :{renk}[{p}/{tp}]")
                        st.caption(f"**Öğrenci:** {soru.get('cevap', '-')}")
                        if renk == "green": st.success(soru.get('yorum'))
                        elif renk == "orange": st.warning(soru.get('yorum'))
                        else: st.error(soru.get('yorum'))

            except Exception as e:
                st.error("Hata oluştu.")
                with st.expander("Detay"):
                    st.write(str(e))
