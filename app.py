import base64
import datetime
import html
import io
import json
import re
from urllib.parse import quote

import pandas as pd
from PIL import Image
import streamlit as st
import streamlit.components.v1 as components

try:
    from num2words import num2words
except ImportError:  # l'app marche, mais sans le total en lettres
    num2words = None

st.set_page_config(page_title="Devis et factures", page_icon="🧾", layout="wide")


# ---------- Réglages (secrets Streamlit, facultatifs) ----------
# access_codes = ["CODE-1", "CODE-2"]   -> active le filigrane tant qu'aucun code valide n'est saisi
# payment_info = "Paye par Bankily au 22 00 00 00 puis envoie la preuve sur WhatsApp."
def secret(key, default=None):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


_codes = secret("access_codes", [])
if isinstance(_codes, str):
    _codes = [_codes]
ACCESS_CODES = [str(c).strip() for c in (_codes or []) if str(c).strip()]
PAYMENT_INFO = str(secret("payment_info", "") or "")

# ---------- Constantes ----------
PALETTE = {"blue": "#1f4e79", "green": "#1b7f5c", "burgundy": "#8e2a3c",
           "orange": "#d9622b", "slate": "#2b3a4a"}
DOCS = ["devis", "proforma", "facture"]
PREFIX = {"devis": "DEV", "proforma": "PRO", "facture": "FAC"}
LANGS = {"Français": "fr", "العربية": "ar"}
LINE_COLS = ["designation", "qte", "pu"]
HIST_COLS = ["numero", "type", "client", "montant", "date", "statut"]
STATUS = ["✅", "⏳", "❌"]
FONTS = "'Amiri', 'Noto Naskh Arabic', 'Segoe UI', Arial, sans-serif"
LOGO_RE = re.compile(r"data:image/png;base64,[A-Za-z0-9+/=]+")

DEFAULTS = {
    "s_name": "", "s_phone": "", "s_email": "", "s_addr": "", "s_nif": "", "s_pay": "",
    "c_name": "", "c_phone": "", "c_addr": "", "notes": "", "f_number": "", "logo": "",
    "doctype": "devis", "color_key": "blue",
    "disc": 0.0, "vat_rate": 16.0, "days": 30,
    "vat_on": False, "auto_no": True,
}

T = {
    "fr": {
        "dir": "ltr", "lang_code": "fr", "title": "Devis et factures",
        "tab_doc": "1. Document", "tab_preview": "2. Aperçu et PDF", "tab_track": "3. Suivi des paiements",
        "type_label": "Type de document",
        "doc_names": {"devis": "Devis", "proforma": "Facture proforma", "facture": "Facture"},
        "doc_titles": {"devis": "DEVIS", "proforma": "FACTURE PROFORMA", "facture": "FACTURE"},
        "color": "Couleur",
        "colors": {"blue": "Bleu", "green": "Vert", "burgundy": "Bordeaux", "orange": "Orange", "slate": "Ardoise"},
        "my_company": "Mon entreprise", "name": "Nom de l'entreprise", "phone": "Téléphone",
        "email": "Email", "nif": "NIF ou RC", "address": "Adresse",
        "payinfo": "Moyens de paiement", "payinfo_ph": "Ex. Bankily 22 00 00 00, virement bancaire",
        "logo": "Logo (facultatif)", "remove_logo": "Retirer le logo",
        "client_section": "Client", "c_name": "Nom du client",
        "c_phone": "Téléphone du client (avec l'indicatif 222)", "c_addr": "Adresse du client",
        "number": "Numéro", "number_auto": "Numérotation automatique", "date": "Date",
        "days_devis": "Validité (jours)", "days_facture": "Délai de paiement (jours)",
        "valid_until": "Valable jusqu'au", "due_date": "Échéance", "to": "Client",
        "lines": "Lignes du document",
        "lines_tip": "Une ligne par produit ou service. Le montant se calcule tout seul.",
        "designation": "Désignation", "qty": "Qté", "unit_price": "Prix unitaire", "amount": "Montant",
        "discount": "Remise (%)", "vat_apply": "Appliquer la TVA", "vat_rate": "Taux de TVA (%)",
        "vat_note": "Vérifie le taux de TVA en vigueur avant de l'utiliser.",
        "notes": "Notes et conditions",
        "subtotal": "Sous-total", "discount_lbl": "Remise", "vat_lbl": "TVA", "total": "Total",
        "in_words": "Montant en lettres", "currency": "MRU", "currency_word": "ouguiyas",
        "dl_pdf": "Télécharger en PDF", "dl_html": "Télécharger en HTML",
        "pdf_error": "L'export PDF n'est pas disponible ici (WeasyPrint). Télécharge le HTML et imprime-le en PDF depuis ton navigateur.",
        "wm": "VERSION GRATUITE",
        "code_label": "Code d'accès (retire le filigrane)", "code_ok": "Code valide : filigrane retiré.",
        "code_bad": "Code incorrect.",
        "payment_info": "Pour obtenir un code d'accès et retirer le filigrane, contacte le créateur de l'app.",
        "wa_btn": "Écrire au client sur WhatsApp",
        "wa_hint": "Le message s'ouvre dans WhatsApp : joins ensuite le PDF téléchargé.",
        "wa_msg": "Bonjour, voici votre {type} n° {number} d'un montant de {total} MRU.",
        "save_btn": "Sauvegarder (fichier)", "load_label": "Recharger un fichier sauvegardé",
        "load_btn": "Charger ce fichier", "load_error": "Fichier invalide.",
        "track_add": "Ajouter ce document au suivi",
        "track_cols": {"numero": "Numéro", "type": "Type", "client": "Client",
                       "montant": "Montant (MRU)", "date": "Date", "statut": "Statut"},
        "track_legend": "✅ payé · ⏳ en attente · ❌ impayé",
        "track_due": "Reste à encaisser (⏳ et ❌)", "signature": "Signature et cachet",
    },
    "ar": {
        "dir": "rtl", "lang_code": "ar", "title": "عروض الأسعار والفواتير",
        "tab_doc": "1. المستند", "tab_preview": "2. المعاينة وPDF", "tab_track": "3. متابعة المدفوعات",
        "type_label": "نوع المستند",
        "doc_names": {"devis": "عرض سعر", "proforma": "فاتورة مبدئية", "facture": "فاتورة"},
        "doc_titles": {"devis": "عرض سعر", "proforma": "فاتورة مبدئية", "facture": "فاتورة"},
        "color": "اللون",
        "colors": {"blue": "أزرق", "green": "أخضر", "burgundy": "عنابي", "orange": "برتقالي", "slate": "رمادي داكن"},
        "my_company": "مؤسستي", "name": "اسم المؤسسة", "phone": "الهاتف",
        "email": "البريد الإلكتروني", "nif": "الرقم الضريبي أو السجل التجاري", "address": "العنوان",
        "payinfo": "طرق الدفع", "payinfo_ph": "مثال: بنكيلي 22 00 00 00، تحويل بنكي",
        "logo": "الشعار (اختياري)", "remove_logo": "إزالة الشعار",
        "client_section": "الزبون", "c_name": "اسم الزبون",
        "c_phone": "هاتف الزبون (مع الرمز 222)", "c_addr": "عنوان الزبون",
        "number": "الرقم", "number_auto": "ترقيم تلقائي", "date": "التاريخ",
        "days_devis": "مدة الصلاحية (أيام)", "days_facture": "مهلة الدفع (أيام)",
        "valid_until": "صالح حتى", "due_date": "تاريخ الاستحقاق", "to": "الزبون",
        "lines": "بنود المستند",
        "lines_tip": "سطر لكل منتج أو خدمة. يُحسب المبلغ تلقائياً.",
        "designation": "البيان", "qty": "الكمية", "unit_price": "سعر الوحدة", "amount": "المبلغ",
        "discount": "التخفيض (%)", "vat_apply": "تطبيق الضريبة على القيمة المضافة", "vat_rate": "نسبة الضريبة (%)",
        "vat_note": "تحقق من النسبة المعمول بها قبل استعمالها.",
        "notes": "ملاحظات وشروط",
        "subtotal": "المجموع الفرعي", "discount_lbl": "التخفيض", "vat_lbl": "الضريبة", "total": "الإجمالي",
        "in_words": "المبلغ بالحروف", "currency": "MRU", "currency_word": "أوقية",
        "dl_pdf": "تحميل PDF", "dl_html": "تحميل HTML",
        "pdf_error": "تصدير PDF غير متاح هنا. حمّل ملف HTML واطبعه كـ PDF من المتصفح.",
        "wm": "نسخة مجانية",
        "code_label": "رمز الوصول (لإزالة العلامة المائية)", "code_ok": "الرمز صحيح: تمت إزالة العلامة المائية.",
        "code_bad": "الرمز غير صحيح.",
        "payment_info": "للحصول على رمز وصول وإزالة العلامة المائية، تواصل مع صاحب التطبيق.",
        "wa_btn": "مراسلة الزبون على واتساب",
        "wa_hint": "تفتح الرسالة في واتساب، ثم أرفق ملف PDF الذي حمّلته.",
        "wa_msg": "مرحباً، هذا {type} رقم {number} بمبلغ {total} MRU.",
        "save_btn": "حفظ (ملف)", "load_label": "إعادة تحميل ملف محفوظ",
        "load_btn": "تحميل هذا الملف", "load_error": "ملف غير صالح.",
        "track_add": "إضافة هذا المستند إلى المتابعة",
        "track_cols": {"numero": "الرقم", "type": "النوع", "client": "الزبون",
                       "montant": "المبلغ (MRU)", "date": "التاريخ", "statut": "الحالة"},
        "track_legend": "✅ مدفوع · ⏳ قيد الانتظار · ❌ غير مدفوع",
        "track_due": "المتبقي للتحصيل (⏳ و ❌)", "signature": "التوقيع والختم",
    },
}


# ---------- Fonctions utilitaires ----------
def esc(v) -> str:
    return html.escape(str(v or "").strip()).replace("\n", "<br>")


def fmt(x) -> str:
    x = float(x)
    txt = f"{int(round(x)):,}" if abs(x - round(x)) < 0.005 else f"{x:,.2f}"
    return txt.replace(",", " ")


def text_on(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#ffffff" if (0.299 * r + 0.587 * g + 0.114 * b) < 160 else "#1a1a1a"


def words(amount: float, lang: str, t: dict) -> str:
    if num2words is None:
        return ""
    try:
        w = num2words(int(round(amount)), lang=lang)
    except Exception:
        return ""
    return f"{w[:1].upper() + w[1:] if lang == 'fr' else w} {t['currency_word']}"


def make_lines(records) -> pd.DataFrame:
    df = pd.DataFrame(records or []).reindex(columns=LINE_COLS)
    for c in ("qte", "pu"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def make_hist(records) -> pd.DataFrame:
    df = pd.DataFrame(records or []).reindex(columns=HIST_COLS)
    df["montant"] = pd.to_numeric(df["montant"], errors="coerce")
    return df


def process_logo(uploaded) -> str:
    try:
        img = Image.open(uploaded).convert("RGBA")
        img.thumbnail((360, 240))
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def compute(lines_df, disc, vat_on, vat_rate):
    rows = []
    for _, r in lines_df.fillna("").iterrows():
        des = str(r["designation"]).strip()
        q = pd.to_numeric(r["qte"], errors="coerce")
        p = pd.to_numeric(r["pu"], errors="coerce")
        if not des and pd.isna(q) and pd.isna(p):
            continue
        q = 1.0 if pd.isna(q) else float(q)
        p = 0.0 if pd.isna(p) else float(p)
        rows.append((des, q, p, q * p))
    sub = sum(r[3] for r in rows)
    disc_amt = sub * float(disc or 0) / 100
    net = sub - disc_amt
    vat = net * float(vat_rate or 0) / 100 if vat_on else 0.0
    return rows, sub, disc_amt, vat, net + vat


def next_number(hist_df, prefix, year) -> int:
    pat = re.compile(rf"^{prefix}-{year}-(\d+)$")
    nums = [int(m.group(1)) for v in hist_df["numero"].astype(str)
            if (m := pat.match(v.strip()))]
    return max(nums, default=0) + 1


# ---------- Construction du document ----------
WM_CSS = (".wm { position: fixed; top: 42%; left: 0; right: 0; text-align: center; font-size: 54pt; "
          "font-weight: bold; color: rgba(0,0,0,.09); transform: rotate(-28deg); z-index: 99; }")


def build_doc(t, lang, d, color, preview=False, watermark=False) -> str:
    rtl = t["dir"] == "rtl"
    end = "left" if rtl else "right"
    on = text_on(color)
    rows, sub, disc_amt, vat, total = compute(d["lines"], d["disc"], d["vat_on"], d["vat_rate"])
    cur = t["currency"]
    until = d["date"] + datetime.timedelta(days=int(d["days"]))
    until_label = t["due_date"] if d["doctype"] == "facture" else t["valid_until"]

    body = "".join(
        f"<tr><td>{esc(des)}</td><td class='n'>{fmt(q)}</td><td class='n'>{fmt(p)}</td>"
        f"<td class='n'>{fmt(a)}</td></tr>" for des, q, p, a in rows)

    tot = f"<tr><td>{t['subtotal']}</td><td class='n'>{fmt(sub)} {cur}</td></tr>"
    if d["disc"]:
        tot += f"<tr><td>{t['discount_lbl']} ({fmt(d['disc'])} %)</td><td class='n'>- {fmt(disc_amt)} {cur}</td></tr>"
    if d["vat_on"]:
        tot += f"<tr><td>{t['vat_lbl']} ({fmt(d['vat_rate'])} %)</td><td class='n'>{fmt(vat)} {cur}</td></tr>"
    tot += f"<tr class='grand'><td>{t['total']}</td><td class='n'>{fmt(total)} {cur}</td></tr>"

    seller = "<br>".join(x for x in (
        f"<b>{esc(d['s_name'])}</b>" if d["s_name"].strip() else "",
        esc(d["s_addr"]), esc(d["s_phone"]), esc(d["s_email"]),
        f"{t['nif']} : {esc(d['s_nif'])}" if d["s_nif"].strip() else "") if x)
    client = "<br>".join(x for x in (
        f"<b>{esc(d['c_name'])}</b>" if d["c_name"].strip() else "",
        esc(d["c_addr"]), esc(d["c_phone"])) if x)
    logo = f'<img class="logo" src="{d["logo"]}" alt="">' if d["logo"] else ""
    w = words(total, lang, t)
    wm = f'<div class="wm">{esc(t["wm"])}</div>' if watermark else ""
    pad = "body { padding: 10mm 12mm; }" if preview else ""
    notes = "".join(f"<p><b>{k}</b><br>{esc(v)}</p>" for k, v in
                    ((t["payinfo"], d["s_pay"]), (t["notes"], d["notes"])) if str(v).strip())

    return f"""<!DOCTYPE html>
<html lang="{t['lang_code']}" dir="{t['dir']}">
<head>
<meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 15mm; }}
  body {{ font-family: {FONTS}; font-size: 10.5pt; line-height: 1.45; color: #222; }}
  {pad}
  {WM_CSS}
  .top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }}
  .logo {{ max-height: 22mm; max-width: 55mm; margin-bottom: 4px; }}
  .title {{ font-size: 24pt; font-weight: bold; color: {color}; line-height: 1.1; }}
  .meta {{ margin-top: 6px; color: #444; }}
  .parties {{ display: flex; justify-content: space-between; gap: 16px; margin: 14px 0; }}
  .box {{ flex: 1; border: 1px solid #d5dbe1; border-radius: 6px; padding: 8px 10px; }}
  .box h4 {{ margin: 0 0 4px; color: {color}; font-size: 10pt; }}
  table.lines {{ width: 100%; border-collapse: collapse; margin-top: 4px; }}
  .lines th {{ background: {color}; color: {on}; padding: 6px 8px; text-align: start; }}
  .lines td {{ padding: 6px 8px; border-bottom: 1px solid #e3e7eb; }}
  .n {{ text-align: {end}; white-space: nowrap; }}
  .lines th.n {{ text-align: {end}; }}
  .totals-wrap {{ display: flex; justify-content: flex-end; margin-top: 10px; }}
  table.totals {{ border-collapse: collapse; min-width: 75mm; }}
  .totals td {{ padding: 4px 8px; }}
  .totals tr.grand td {{ background: {color}; color: {on}; font-weight: bold; font-size: 12pt; }}
  .words {{ margin-top: 12px; padding: 8px 10px; background: #f2f5f8; border-radius: 6px; }}
  .sign {{ margin-top: 22mm; display: flex; justify-content: flex-end; }}
  .sign div {{ width: 60mm; border-top: 1px solid #888; padding-top: 4px; text-align: center; color: #555; }}
  p {{ margin: 8px 0 0; }}
</style>
</head>
<body>
  {wm}
  <div class="top">
    <div>{logo}<div>{seller}</div></div>
    <div style="text-align:{end}">
      <div class="title">{esc(t['doc_titles'][d['doctype']])}</div>
      <div class="meta">N° {esc(d['number'])}<br>{t['date']} : {d['date'].strftime('%d/%m/%Y')}<br>
        {until_label} : {until.strftime('%d/%m/%Y')}</div>
    </div>
  </div>
  <div class="parties"><div class="box"><h4>{t['to']}</h4>{client}</div></div>
  <table class="lines">
    <tr><th>{t['designation']}</th><th class="n">{t['qty']}</th><th class="n">{t['unit_price']}</th><th class="n">{t['amount']}</th></tr>
    {body}
  </table>
  <div class="totals-wrap"><table class="totals">{tot}</table></div>
  {f'<div class="words"><b>{t["in_words"]} :</b> {esc(w)}</div>' if w else ''}
  {notes}
  <div class="sign"><div>{t['signature']}</div></div>
</body>
</html>"""


def make_pdf(html_str: str) -> bytes:
    from weasyprint import HTML  # importé ici : l'app marche même sans WeasyPrint
    return HTML(string=html_str).write_pdf()


# ---------- État de l'application ----------
s = st.session_state


def apply_state(data: dict):
    for k, dv in DEFAULTS.items():
        v = data.get(k, dv)
        if isinstance(dv, bool):
            v = v if isinstance(v, bool) else dv
        elif isinstance(dv, float):
            v = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else dv
        elif isinstance(dv, int):
            v = v if isinstance(v, int) and not isinstance(v, bool) else dv
        else:
            v = v if isinstance(v, str) else dv
        s[k] = v
    if s["logo"] and not LOGO_RE.fullmatch(s["logo"]):
        s["logo"] = ""
    if s["color_key"] not in PALETTE:
        s["color_key"] = "blue"
    if s["doctype"] not in DOCS:
        s["doctype"] = "devis"
    if data.get("lang_label") in LANGS:
        s["lang_label"] = data["lang_label"]
    lines = data.get("lines")
    hist = data.get("hist")
    s["df_lines"] = make_lines(lines if isinstance(lines, list) else [])
    s["df_hist"] = make_hist(hist if isinstance(hist, list) else [])
    s["logo_src"] = None
    for k in ("ver", "hist_ver", "logo_ver"):
        s[k] = s.get(k, 0) + 1


def load_file():
    up = s.get(f"load_file_{s.get('ver', 0)}")
    if up is None:
        return
    try:
        data = json.loads(up.getvalue().decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError
    except Exception:
        s["load_error"] = True
        return
    s["load_error"] = False
    apply_state(data)


if "ver" not in s:
    s["lang_label"] = "Français"
    s["f_date"] = datetime.date.today()
    s["load_error"] = False
    apply_state({})

# ---------- Barre latérale ----------
st.sidebar.radio("Langue / اللغة", list(LANGS), key="lang_label")
lang = LANGS[s["lang_label"]]
t = T[lang]
ver, hver = s["ver"], s["hist_ver"]

unlocked = True
if ACCESS_CODES:
    code = st.sidebar.text_input(t["code_label"], type="password", key="access_code")
    unlocked = code.strip() in ACCESS_CODES
    if code.strip():
        (st.sidebar.success if unlocked else st.sidebar.error)(t["code_ok"] if unlocked else t["code_bad"])
    if not unlocked:
        st.sidebar.info(PAYMENT_INFO or t["payment_info"])
watermark = bool(ACCESS_CODES) and not unlocked

# ---------- Page principale ----------
st.title(f"🧾 {t['title']}")
tab_doc, tab_prev, tab_track = st.tabs([t["tab_doc"], t["tab_preview"], t["tab_track"]])

with tab_doc:
    c1, c2 = st.columns(2)
    c1.radio(t["type_label"], DOCS, key="doctype",
             format_func=lambda k: t["doc_names"][k], horizontal=True)
    c2.selectbox(t["color"], list(PALETTE), key="color_key", format_func=lambda k: t["colors"][k])

    with st.expander(t["my_company"], expanded=not s["s_name"]):
        a, b = st.columns(2)
        a.text_input(t["name"], key="s_name")
        b.text_input(t["phone"], key="s_phone")
        a.text_input(t["email"], key="s_email")
        b.text_input(t["nif"], key="s_nif")
        st.text_input(t["address"], key="s_addr")
        st.text_area(t["payinfo"], key="s_pay", height=70, placeholder=t["payinfo_ph"])
        up = st.file_uploader(t["logo"], type=["png", "jpg", "jpeg"], key=f"logo_up_{s['logo_ver']}")
        if up is not None and s.get("logo_src") != getattr(up, "file_id", up.name):
            s["logo"] = process_logo(up)
            s["logo_src"] = getattr(up, "file_id", up.name)
        if s["logo"]:
            lc1, lc2 = st.columns([1, 4])
            lc1.image(s["logo"], width=110)
            if lc2.button(t["remove_logo"]):
                s["logo"] = ""
                s["logo_src"] = None
                s["logo_ver"] += 1
                st.rerun()

    with st.expander(t["client_section"], expanded=True):
        a, b = st.columns(2)
        a.text_input(t["c_name"], key="c_name")
        b.text_input(t["c_phone"], key="c_phone")
        st.text_input(t["c_addr"], key="c_addr")

    d1, d2, d3 = st.columns(3)
    d1.date_input(t["date"], key="f_date")
    d2.number_input(t["days_facture"] if s["doctype"] == "facture" else t["days_devis"],
                    min_value=0, max_value=365, step=1, key="days")
    prefix, year = PREFIX[s["doctype"]], s["f_date"].year
    auto_number = f"{prefix}-{year}-{next_number(s['df_hist'], prefix, year):03d}"
    d3.checkbox(t["number_auto"], key="auto_no")
    d3.text_input(t["number"], key="f_number", disabled=s["auto_no"],
                  placeholder=auto_number if s["auto_no"] else "")
    number = auto_number if s["auto_no"] else s["f_number"]

    st.subheader(t["lines"])
    st.caption(t["lines_tip"])
    ed_lines = st.data_editor(
        s["df_lines"], num_rows="dynamic", key=f"ed_lines_{ver}",
        column_config={
            "designation": t["designation"],
            "qte": st.column_config.NumberColumn(t["qty"], min_value=0.0),
            "pu": st.column_config.NumberColumn(t["unit_price"], min_value=0.0),
        })

    e1, e2, e3 = st.columns(3)
    e1.number_input(t["discount"], min_value=0.0, max_value=100.0, step=1.0, key="disc")
    e2.checkbox(t["vat_apply"], key="vat_on")
    e3.number_input(t["vat_rate"], min_value=0.0, max_value=100.0, step=1.0,
                    key="vat_rate", disabled=not s["vat_on"])
    if s["vat_on"]:
        e3.caption(t["vat_note"])
    st.text_area(t["notes"], key="notes", height=80)

data = {
    "doctype": s["doctype"], "number": number, "date": s["f_date"], "days": s["days"],
    "disc": s["disc"], "vat_on": s["vat_on"], "vat_rate": s["vat_rate"],
    "lines": ed_lines, "logo": s["logo"], "notes": s["notes"],
    **{k: s[k] for k in ("s_name", "s_phone", "s_email", "s_addr", "s_nif", "s_pay",
                         "c_name", "c_phone", "c_addr")},
}
color = PALETTE[s["color_key"]]
rows, sub, disc_amt, vat, total = compute(ed_lines, s["disc"], s["vat_on"], s["vat_rate"])
doc_html = build_doc(t, lang, data, color, watermark=watermark)

with tab_doc:
    st.metric(t["total"], f"{fmt(total)} {t['currency']}")

with tab_prev:
    components.html(build_doc(t, lang, data, color, preview=True, watermark=watermark),
                    height=900, scrolling=True)
    fname = f"{PREFIX[s['doctype']].lower()}-{number}".replace("/", "-")
    st.download_button(t["dl_html"], doc_html, file_name=f"{fname}.html", mime="text/html")
    try:
        st.download_button(t["dl_pdf"], make_pdf(doc_html), file_name=f"{fname}.pdf", mime="application/pdf")
    except Exception:
        st.info(t["pdf_error"])
    digits = re.sub(r"\D", "", s["c_phone"])
    msg = t["wa_msg"].format(type=t["doc_names"][s["doctype"]].lower(), number=number, total=fmt(total))
    if s["s_name"].strip():
        msg += f" — {s['s_name'].strip()}"
    st.link_button(t["wa_btn"], f"https://wa.me/{digits}?text={quote(msg)}")
    st.caption(t["wa_hint"])

with tab_track:
    st.caption(t["track_legend"])
    tc = t["track_cols"]
    ed_hist = st.data_editor(
        s["df_hist"], num_rows="dynamic", key=f"ed_hist_{hver}",
        column_config={
            "numero": tc["numero"], "type": tc["type"], "client": tc["client"],
            "montant": st.column_config.NumberColumn(tc["montant"], min_value=0.0),
            "date": tc["date"],
            "statut": st.column_config.SelectboxColumn(tc["statut"], options=STATUS),
        })
    unpaid = pd.to_numeric(ed_hist.loc[ed_hist["statut"].isin(["⏳", "❌"]), "montant"],
                           errors="coerce").sum()
    st.metric(t["track_due"], f"{fmt(unpaid)} {t['currency']}")
    if st.button(t["track_add"]):
        row = {"numero": number, "type": t["doc_names"][s["doctype"]], "client": s["c_name"],
               "montant": round(total, 2), "date": s["f_date"].strftime("%d/%m/%Y"), "statut": "⏳"}
        s["df_hist"] = pd.concat([ed_hist, pd.DataFrame([row])], ignore_index=True)[HIST_COLS]
        s["hist_ver"] += 1
        st.rerun()

# ---------- Sauvegarde et rechargement ----------
payload = {
    "version": 1, "lang_label": s["lang_label"],
    **{k: s[k] for k in DEFAULTS},
    "lines": ed_lines.fillna("").to_dict("records"),
    "hist": ed_hist.fillna("").to_dict("records"),
}
with st.sidebar:
    st.divider()
    st.download_button(t["save_btn"], json.dumps(payload, ensure_ascii=False, default=str),
                       file_name="devis-factures.json", mime="application/json")
    st.file_uploader(t["load_label"], type=["json"], key=f"load_file_{ver}")
    st.button(t["load_btn"], on_click=load_file)
    if s.get("load_error"):
        st.error(t["load_error"])
