---
title: sample-fa-en
source: sample-fa-en.docx
lang: fa
purpose: llm
tables: 0
figures: 0
---

# نمونه سند فارسی و انگلیسی برای MD Maker

این سند برای آزمایش تبدیل PDF یا DOCX به Markdown آماده شده است. هدف آن بررسی درست بودن تیترها، متن فارسی، متن انگلیسی، فهرست‌ها، جدول‌ها، اعداد، کد و ترکیب راست‌به‌چپ و چپ‌به‌راست است.

## هدف سند

این نمونه نشان می‌دهد که یک ابزار تبدیل اسناد باید بتواند ساختار منطقی متن را حفظ کند؛ حتی وقتی یک فایل هم‌زمان شامل زبان فارسی، انگلیسی، شماره نسخه، آدرس وب، جدول و کد باشد.

### اطلاعات نمونه

| مورد | مقدار |
| --- | --- |
| نام ابزار | MD Maker |
| نوع ورودی | PDF و DOCX |
| نوع خروجی | Markdown |
| زبان‌های نمونه | فارسی و English |
| جهت نوشتار | RTL و LTR |
| شماره نسخه | 1.0.0 |
| تاریخ آزمایش | 2026-08-20 |

### متن ترکیبی فارسی و انگلیسی

این ابزار یک فایل PDF یا DOCX را به Markdown تبدیل می‌کند. خروجی برای استفاده در LLM، RAG، جست‌وجوی معنایی، آرشیو دانش و مطالعه مناسب است.

برای مثال، آدرس https://example.com/docs، شناسهٔ نسخه v2.4.1، IP مانند 192.168.1.10 و شماره پورت 40100 باید بدون به‌هم‌ریختگی در خروجی باقی بمانند.

## تیترهای چندسطحی

### عنوان سطح ۳

این سطح برای زیرمجموعه‌های یک موضوع اصلی مناسب است. به عنوان مثال، در یک مستند فنی می‌تواند دربارهٔ نحوهٔ نصب، تنظیمات یا تبدیل فایل‌ها توضیح دهد.

#### عنوان سطح ۴

در این سطح جزئیات عملی‌تر قرار می‌گیرند. برای مثال می‌توان دربارهٔ تنظیم گزینه‌های تبدیل یا بررسی خروجی Markdown صحبت کرد.

##### عنوان سطح ۵

این سطح برای نکات دقیق‌تر، استثناها یا راهنمایی‌های تکمیلی مفید است.

###### عنوان سطح ۶

از این سطح فقط برای موارد واقعاً جزئی استفاده کنید، چون استفادهٔ زیاد از تیترهای عمیق خوانایی متن را کاهش می‌دهد.

## فهرست‌های بولتی

- سطح ۱: تبدیل فایل PDF

  - سطح ۲: استخراج متن منطقی

    - سطح ۳: تصحیح ترتیب خواندن RTL

  - سطح ۲: تشخیص جدول

    - سطح ۳: ایجاد جدول Markdown

- سطح ۱: تبدیل فایل DOCX

  - سطح ۲: خواندن تیترها و پاراگراف‌ها

  - سطح ۲: استخراج جدول‌های Word

- سطح ۱: تولید خروجی مناسب LLM

## فهرست‌های شماره‌دار

1. فایل مورد نظر خود را انتخاب کنید.
  1.1 فایل می‌تواند PDF یا DOCX باشد.
  1.2 می‌توانید یک فایل، چند فایل یا یک پوشه را انتخاب کنید.

2. حالت تبدیل را انتخاب کنید.
  2.1 حالت llm برای استفاده در مدل‌های زبانی مناسب است.
  2.2 حالت reading برای مطالعه و مشاهدهٔ خروجی مناسب است.

3. روی Convert کلیک کنید.
  3.1 فایل Markdown در پوشهٔ خروجی ایجاد می‌شود.

## جدول نمونه: برنامه تبدیل فایل‌ها

| نام فایل | نوع فایل | زبان اصلی | وضعیت تبدیل | توضیح |
| --- | --- | --- | --- | --- |
| راهنمای کاربر.pdf | PDF | فارسی | آماده | شامل متن RTL و جدول |
| network-spec.docx | DOCX | English | آماده | شامل تیتر، کد و جدول |
| گزارش ترکیبی.pdf | PDF | فارسی + English | نیازمند بررسی | شامل نمودار و متن دو زبانه |
| سند اسکن‌شده.pdf | PDF Scan | فارسی | OCR لازم است | متن قابل انتخاب ندارد |

## جدول نمونه: مقایسهٔ خروجی‌ها

| ویژگی | خروجی LLM | خروجی Reading |
| --- | --- | --- |
| هدف اصلی | بازیابی و پردازش توسط مدل | مطالعهٔ آسان‌تر توسط انسان |
| تقسیم‌بندی بر اساس تیتر | اختیاری | معمولاً غیرفعال |
| مناسب برای RAG | بله | بله، با بررسی بیشتر |
| تصاویر جدول | اختیاری | اختیاری |
| حفظ فایل منبع | توصیه می‌شود | توصیه می‌شود |

## نمونه کد و اطلاعات فنی

**json**

{

"purpose": "llm",

"persian_digits": true,

"table_images": true,

"split_llm": true

}

**text**

Input:  input/guide-fa.pdf

Output: output/llm/guide-fa/guide-fa.md

Log:    output/llm/guide-fa/convert.log

## پاراگراف پایانی

این سند نمونه کمک می‌کند بررسی کنید که تبدیل‌کننده، ساختار متن، جهت نوشتار، جدول‌ها، فهرست‌ها و محتوای ترکیبی فارسی و انگلیسی را به‌درستی حفظ می‌کند. در اسناد مهم، به‌خصوص PDFهای اسکن‌شده، فایل‌های دارای فونت غیرمعمول، جدول‌های پیچیده یا متن‌های ترکیبی، خروجی Markdown را بازبینی کنید.

# MD Maker Persian and English Test Document

This document is prepared to test PDF or DOCX conversion to Markdown. Its purpose is to verify headings, Persian text, English text, lists, tables, numbers, code blocks, and mixed right-to-left and left-to-right content.

## Document purpose

This sample demonstrates that a document-conversion tool should preserve the logical structure of content, even when one file includes Persian and English text, version numbers, URLs, tables, and code.

### Sample information

| Item | Value |
| --- | --- |
| Tool name | MD Maker |
| Input types | PDF and DOCX |
| Output type | Markdown |
| Sample languages | Persian and English |
| Writing directions | RTL and LTR |
| Version | 1.0.0 |
| Test date | 2026-08-20 |

### Mixed Persian and English content

MD Maker converts a PDF or DOCX file into Markdown. The output is suitable for LLM workflows, RAG, semantic search, knowledge archiving, and reading.

For example, a URL such as https://example.com/docs, a version identifier such as v2.4.1, an IP address such as 192.168.1.10, and a port number such as 40100 should remain intact in the converted output.

## Multi-level headings

### Level 3 heading

This level is useful for subtopics under a main subject. In a technical document, it can describe installation, configuration, or file-conversion steps.

#### Level 4 heading

This level contains more practical details. For example, it can explain conversion options or how to review Markdown output.

##### Level 5 heading

This level is useful for precise notes, exceptions, or additional guidance.

###### Level 6 heading

Use this level only for genuinely small details, because excessive heading depth reduces readability.

## Bullet lists

- Level 1: Convert a PDF file

  - Level 2: Extract logical text

    - Level 3: Repair RTL reading order

  - Level 2: Detect tables

    - Level 3: Generate Markdown tables

- Level 1: Convert a DOCX file

  - Level 2: Read headings and paragraphs

  - Level 2: Extract native Word tables

- Level 1: Generate LLM-ready output

## Numbered lists

1. Select the document you want to convert.
  1.1 The file can be a PDF or DOCX document.
  1.2 You can select one file, multiple files, or a folder.

2. Select the conversion mode.
  2.1 The llm mode is intended for language-model workflows.
  2.2 The reading mode is intended for easier human review.

3. Click Convert.
  3.1 The Markdown file is created in the output folder.

## Sample table: File conversion plan

| File name | File type | Primary language | Conversion status | Notes |
| --- | --- | --- | --- | --- |
| user-guide-fa.pdf | PDF | Persian | Ready | Contains RTL text and a table |
| network-spec.docx | DOCX | English | Ready | Contains headings, code, and tables |
| bilingual-report.pdf | PDF | Persian + English | Review needed | Contains a chart and bilingual text |
| scanned-document.pdf | Scanned PDF | Persian | OCR required | Does not contain selectable text |

## Sample table: Output comparison

| Feature | LLM output | Reading output |
| --- | --- | --- |
| Primary goal | Retrieval and model processing | Easier human reading |
| Heading-based splitting | Optional | Usually disabled |
| Suitable for RAG | Yes | Yes, after review |
| Table images | Optional | Optional |
| Keep original source file | Recommended | Recommended |

## Code and technical information

**json**

{

"purpose": "llm",

"persian_digits": true,

"table_images": true,

"split_llm": true

}

**text**

Input:  input/guide-fa.pdf

Output: output/llm/guide-fa/guide-fa.md

Log:    output/llm/guide-fa/convert.log

## Closing paragraph

This test document helps verify that the converter preserves document structure, writing direction, tables, lists, and mixed Persian-English content. For important documents—especially scanned PDFs, files with unusual fonts, complex tables, or mixed-direction text—review the final Markdown output before relying on it.
