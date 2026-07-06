import asyncio
from pyrogram import filters
from devgagan import app, sex
from telethon import functions
from telethon.tl.types import InputRichMessageMarkdown

SIGNATURE = "\n\n---\n🛡️ **Owner:** [𝗖𝗛𝗢𝗦𝗘𝗡 𝗢𝗡𝗘 ⚝](https://t.me/CHOSEN_ONEx_bot)"

START_TEXT = r"""
# 🎓 Ultimate Study & Math Reference Bot

Welcome! I'm formatted using **Telegram's Rich Markdown** (tables, LaTeX math, checklists, quotes, code).

Here is the directory of available reference commands:

- `/math` - Higher Mathematics (Algebra, Calculus, Statistics)
- `/arithmetic` - Percentage, Ratio, Interest & Proportion formulas
- `/geometry` - Area, Perimeter, and Volume of 2D/3D shapes
- `/cheatsheet` - Formula quick reference table (Physics, Chemistry & Math)
- `/reasoning` - Direction & Distance Reasoning Tricks & Formulas
- `/coding` - Coding-Decoding Reasoning logic & Shift Diagram
- `/chart` - Alphabet A-Z Position Reference Grid Chart

*Use these commands to quickly pull up study materials anytime!*""" + SIGNATURE

MATH_TEXT = r"""
# 📐 Higher Mathematics Formulas

## 1. Algebra & Series

* **Quadratic Formula:**
  If $ax^2 + bx + c = 0$, then:
  
  $$x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$$
  
* **Binomial Theorem:**
  $$(a+b)^n = \sum_{k=0}^{n} \binom{n}{k} a^{n-k} b^k$$

## 2. Calculus

* **Derivative Definition:**
  $$f'(x) = \lim_{h \to 0} \frac{f(x+h) - f(x)}{h}$$
  
* **Integration by Parts:**
  $$\int u\,dv = uv - \int v\,du$$

## 3. Probability & Statistics

* **Bayes' Theorem:**
  $$P(A|B) = \frac{P(B|A) \cdot P(A)}{P(B)}$$
  
* **Standard Deviation (Sample):**
  $$s = \sqrt{\frac{\sum_{i=1}^{n} (x_i - \bar{x})^2}{n-1}}$$""" + SIGNATURE

ARITHMETIC_TEXT = r"""
# 🧮 Arithmetic: Percentages & Ratios

## 1. Percentages

* **Percentage Change:**
  $$\text{Percentage Change} = \frac{\text{New Value} - \text{Old Value}}{\text{Old Value}} \times 100\%$$
  
* **Profit & Loss Percentage:**
  $$\text{Profit \%} = \frac{\text{Selling Price} - \text{Cost Price}}{\text{Cost Price}} \times 100\%$$
  
  $$\text{Loss \%} = \frac{\text{Cost Price} - \text{Selling Price}}{\text{Cost Price}} \times 100\%$$
  
* **Simple Interest:**
  $$I = \frac{P \cdot r \cdot t}{100}$$
  
* **Compound Interest:**
  $$A = P \left(1 + \frac{r}{n}\right)^{nt}$$
  
  _Where $A$ is the total amount, $P$ is principal, $r$ is interest rate, $n$ is compounding frequency, and $t$ is time._

## 2. Ratio & Proportion

* **Ratio Equality (Proportion):**
  $$\frac{a}{b} = \frac{c}{d} \implies a \cdot d = b \cdot c$$
  
* **Compound Ratio:**
  $$\text{Compound of } a:b \text{ and } c:d \text{ is } (a \cdot c) : (b \cdot d)$$
  
* **Direct Variation:** $y = k \cdot x$ (where $k$ is constant)

* **Inverse Variation:** $y = \frac{k}{x} \implies x \cdot y = k$""" + SIGNATURE

GEOMETRY_TEXT = r"""
# 📏 Geometry: Area & Volume Formulas

## 1. 2D Shapes (Area & Perimeter)

* **Circle:**
  * $\text{Area} = \pi r^2$
  * $\text{Circumference} = 2\pi r$
  
* **Triangle:**
  * $\text{Area} = \frac{1}{2} \cdot b \cdot h$
  * $\text{Heron's Formula:} \sqrt{s(s-a)(s-b)(s-c)} \quad \text{where } s = \frac{a+b+c}{2}$

## 2. 3D Solids (Volume & Surface Area)

| Solid Shape | Volume Formula | Total Surface Area (TSA) |
|:---|:---:|:---|
| **Sphere** | $V = \frac{4}{3}\pi r^3$ | $A = 4\pi r^2$ |
| **Cylinder** | $V = \pi r^2 h$ | $A = 2\pi r(r + h)$ |
| **Cone** | $V = \frac{1}{3}\pi r^2 h$ | $A = \pi r(r + \sqrt{r^2 + h^2})$ |
| **Cube** | $V = a^3$ | $A = 6a^2$ |
| **Rect. Prism** | $V = l \cdot w \cdot h$ | $A = 2(lw + lh + wh)$ |""" + SIGNATURE

CHEATSHEET_TEXT = r"""
# 📊 Subject Cheat Sheet

| Subject | Topic | Key Formula | Explanation |
|:---|:---|:---:|:---|
| **Physics** | Gravity | $F = G \frac{m_1 m_2}{r^2}$ | Universal Gravitational Force |
| **Physics** | Einstein | $E = mc^2$ | Mass-energy Equivalence |
| **Chemistry**| Ideal Gas | $PV = nRT$ | Pressure, Vol, Temp relation |
| **Chemistry**| pH Value | $\text{pH} = -\log_{10}[\text{H}^+]$ | Acidity/Alkalinity measure |
| **Math** | Euler Poly | $V - E + F = 2$ | Vertices, Edges, Faces |
| **Math** | Euler Identity| $e^{i\pi} + 1 = 0$ | Linking 5 major constants |""" + SIGNATURE

REASONING_TEXT = r"""
# 🧭 Direction & Distance Tricks & Formulas

## 1. The 8 Main Directions

```
       N (North)
    NW  │  NE
      \ │ /
W ──────┼────── E (East)
(West) /│\
      / │ \
    SW  │  SE
       S (South)
```

## 2. Key Rules & Tricks

* **Pythagoras Theorem:** For finding the shortest distance:
  $$H^2 = B^2 + P^2 \implies H = \sqrt{B^2 + P^2}$$
  
  _Where $H$ is the hypotenuse (shortest distance), $B$ is the base, and $P$ is the perpendicular._
  
* **Turn Angles:**
  * Left turn = $90^\circ$ Counter-Clockwise (CCW)
  * Right turn = $90^\circ$ Clockwise (CW)
  
* **Shadow Cases:**
  * **Sunrise (East):** Shadow is always in the **West**.
  * **Sunset (West):** Shadow is always in the **East**.
  * **Noon (12 PM):** No shadow is formed.""" + SIGNATURE

CODING_TEXT = r"""
# 🔐 Coding-Decoding Reasoning Guide

## ❓ Problem Example

In a certain secret code language:
> **"STUDY"** is coded as **"VwxgB"**

**How will the word "SMART" be coded in that same language?**

---

## 🗺️ Logic Shift Diagram

Here is how each letter shifts forward by **+3 positions** in the alphabet:

```
Input Word:  S   T   U   D   Y
             │   │   │   │   │
Shift Value: +3  +3  +3  +3  +3
             ▼   ▼   ▼   ▼   ▼
Coded Word:  V   W   X   G   B
```

*(Note: For Y + 3, we wrap around: Y ➔ Z ➔ A ➔ B)*

---

## 💡 Step-by-Step Decoding for "SMART"

Applying the exact same **+3 shift** logic to each letter of **"SMART"**:

| Letter | Shift Logic | Resulting Letter |
|:---:|:---:|:---:|
| **S** | S + 3 | **V** |
| **M** | M + 3 | **P** |
| **A** | A + 3 | **D** |
| **R** | R + 3 | **U** |
| **T** | T + 3 | **W** |

### 📐 Final Coded Answer:

> **"SMART"** ➔ **"VpdUW"**""" + SIGNATURE

CHART_TEXT = r"""
# 🔠 Alphabet Position & Opposites Reference Chart

### (1) English alphabets Position from left to right :-

| **A** | **B** | **C** | **D** | **E** | **F** | **G** | **H** | **I** | **J** | **K** | **L** | **M** |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `1` | `2` | `3` | `4` | `5` | `6` | `7` | `8` | `9` | `10` | `11` | `12` | `13` |

| **N** | **O** | **P** | **Q** | **R** | **S** | **T** | **U** | **V** | **W** | **X** | **Y** | **Z** |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `14` | `15` | `16` | `17` | `18` | `19` | `20` | `21` | `22` | `23` | `24` | `25` | `26` |

---

### (2) English alphabets position from Right to left :-

| **Z** | **Y** | **X** | **W** | **V** | **U** | **T** | **S** | **R** | **Q** | **P** | **O** | **N** |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `1` | `2` | `3` | `4` | `5` | `6` | `7` | `8` | `9` | `10` | `11` | `12` | `13` |

| **M** | **L** | **K** | **J** | **I** | **H** | **G** | **F** | **E** | **D** | **C** | **B** | **A** |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `14` | `15` | `16` | `17` | `18` | `19` | `20` | `21` | `22` | `23` | `24` | `25` | `26` |

---

### (3) Series of opposite English Alphabets :-

| **A** | **B** | **C** | **D** | **E** | **F** | **G** | **H** | **I** | **J** | **K** | **L** | **M** |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Z** | **Y** | **X** | **W** | **V** | **U** | **T** | **S** | **R** | **Q** | **P** | **O** | **N** |

| **N** | **O** | **P** | **Q** | **R** | **S** | **T** | **U** | **V** | **W** | **X** | **Y** | **Z** |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **M** | **L** | **K** | **J** | **I** | **H** | **G** | **F** | **E** | **D** | **C** | **B** | **A** |

> **Tip:** Memorizing this chart or writing it down quickly in exams will save you valuable time!""" + SIGNATURE

@app.on_message(filters.command(["math", "maths"]))
async def maths_menu_handler(client, message):
    chat_id = message.chat.id
    try:
        await sex(functions.messages.SendMessageRequest(
            peer=chat_id,
            message="Study Reference Menu",
            rich_message=InputRichMessageMarkdown(markdown=START_TEXT),
        ))
    except Exception as ex:
        print(f"Error in maths_menu_handler: {ex}")

@app.on_message(filters.command("algebra"))
async def algebra_handler(client, message):
    chat_id = message.chat.id
    try:
        await sex(functions.messages.SendMessageRequest(
            peer=chat_id,
            message="Mathematics Formulas",
            rich_message=InputRichMessageMarkdown(markdown=MATH_TEXT),
        ))
    except Exception as ex:
        print(f"Error in algebra_handler: {ex}")

@app.on_message(filters.command("arithmetic"))
async def arithmetic_handler(client, message):
    chat_id = message.chat.id
    try:
        await sex(functions.messages.SendMessageRequest(
            peer=chat_id,
            message="Arithmetic Formulas",
            rich_message=InputRichMessageMarkdown(markdown=ARITHMETIC_TEXT),
        ))
    except Exception as ex:
        print(f"Error in arithmetic_handler: {ex}")

@app.on_message(filters.command("geometry"))
async def geometry_handler(client, message):
    chat_id = message.chat.id
    try:
        await sex(functions.messages.SendMessageRequest(
            peer=chat_id,
            message="Geometry Formulas",
            rich_message=InputRichMessageMarkdown(markdown=GEOMETRY_TEXT),
        ))
    except Exception as ex:
        print(f"Error in geometry_handler: {ex}")

@app.on_message(filters.command("cheatsheet"))
async def cheatsheet_handler(client, message):
    chat_id = message.chat.id
    try:
        await sex(functions.messages.SendMessageRequest(
            peer=chat_id,
            message="Cheat Sheet",
            rich_message=InputRichMessageMarkdown(markdown=CHEATSHEET_TEXT),
        ))
    except Exception as ex:
        print(f"Error in cheatsheet_handler: {ex}")

@app.on_message(filters.command("reasoning"))
async def reasoning_handler(client, message):
    chat_id = message.chat.id
    try:
        await sex(functions.messages.SendMessageRequest(
            peer=chat_id,
            message="Direction & Distance Reasoning",
            rich_message=InputRichMessageMarkdown(markdown=REASONING_TEXT),
        ))
    except Exception as ex:
        print(f"Error in reasoning_handler: {ex}")

@app.on_message(filters.command("coding"))
async def coding_handler(client, message):
    chat_id = message.chat.id
    try:
        await sex(functions.messages.SendMessageRequest(
            peer=chat_id,
            message="Coding-Decoding Guide",
            rich_message=InputRichMessageMarkdown(markdown=CODING_TEXT),
        ))
    except Exception as ex:
        print(f"Error in coding_handler: {ex}")

@app.on_message(filters.command("chart"))
async def chart_handler(client, message):
    chat_id = message.chat.id
    try:
        await sex(functions.messages.SendMessageRequest(
            peer=chat_id,
            message="Alphabet Position Reference Chart",
            rich_message=InputRichMessageMarkdown(markdown=CHART_TEXT),
        ))
    except Exception as ex:
        print(f"Error in chart_handler: {ex}")

@app.on_message(filters.command("myrich"))
async def myrich_handler(client, message):
    chat_id = message.chat.id
    text = ""
    if message.text:
        parts = message.text.split(None, 1)
        if len(parts) > 1:
            text = parts[1].strip()
            
    if not text:
        help_text = (
            "💡 **How to use `/myrich`:**\n\n"
            "Send `/myrich` followed by your markdown text to generate a rich message.\n\n"
            "**Example:**\n"
            "```\n"
            "/myrich # 📅 My Timetable\n"
            "| Day | Subject |\n"
            "|:---:|:---:|\n"
            "| Mon | Physics |\n"
            "| Tue | Math |\n"
            "```"
        )
        await message.reply_text(help_text)
        return
        
    try:
        await sex(functions.messages.SendMessageRequest(
            peer=chat_id,
            message="Rich Message Preview",
            rich_message=InputRichMessageMarkdown(markdown=text),
        ))
    except Exception as ex:
        await message.reply_text(f"❌ **Error parsing markdown:** `{str(ex)}`")
