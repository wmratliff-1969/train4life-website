"""
Train4Life Admin PDF Generator
Generates two professional PDFs for the Train4Life admin panel.
"""

import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.platypus.frames import Frame
from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# ── Colors ────────────────────────────────────────────────────────────────────
RED      = colors.HexColor('#CC0000')
DARK     = colors.HexColor('#1a1a1a')
GRAY     = colors.HexColor('#71717a')
LIGHT_GRAY = colors.HexColor('#f4f4f5')
MID_GRAY = colors.HexColor('#e4e4e7')
WHITE    = colors.white
BLACK    = colors.black

# ── Output paths ──────────────────────────────────────────────────────────────
GUIDE_PATH = '/Users/mratliff/PycharmProjects/train4life-website/static/admin/Train4Life_Admin_Complete_Guide.pdf'
SCRIPT_PATH = '/Users/mratliff/PycharmProjects/train4life-website/static/admin/Train4Life_Admin_Walkthrough_Script.pdf'

os.makedirs(os.path.dirname(GUIDE_PATH), exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
#  Shared helpers
# ══════════════════════════════════════════════════════════════════════════════

def build_styles():
    """Return a dict of named ParagraphStyles."""
    base = getSampleStyleSheet()

    styles = {}

    styles['title'] = ParagraphStyle(
        'T4LTitle',
        fontName='Helvetica-Bold',
        fontSize=34,
        textColor=RED,
        spaceAfter=6,
        leading=40,
        alignment=TA_CENTER,
    )
    styles['subtitle'] = ParagraphStyle(
        'T4LSubtitle',
        fontName='Helvetica',
        fontSize=13,
        textColor=GRAY,
        spaceAfter=4,
        leading=18,
        alignment=TA_CENTER,
    )
    styles['badge'] = ParagraphStyle(
        'T4LBadge',
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=RED,
        spaceAfter=0,
        alignment=TA_CENTER,
    )
    styles['section_header'] = ParagraphStyle(
        'T4LSectionHeader',
        fontName='Helvetica-Bold',
        fontSize=15,
        textColor=RED,
        spaceBefore=18,
        spaceAfter=4,
        leading=20,
    )
    styles['subsection'] = ParagraphStyle(
        'T4LSubsection',
        fontName='Helvetica-Bold',
        fontSize=11,
        textColor=DARK,
        spaceBefore=10,
        spaceAfter=3,
        leading=15,
    )
    styles['body'] = ParagraphStyle(
        'T4LBody',
        fontName='Helvetica',
        fontSize=10.5,
        textColor=DARK,
        spaceAfter=5,
        leading=15,
    )
    styles['body_gray'] = ParagraphStyle(
        'T4LBodyGray',
        fontName='Helvetica',
        fontSize=10,
        textColor=GRAY,
        spaceAfter=4,
        leading=14,
    )
    styles['bullet'] = ParagraphStyle(
        'T4LBullet',
        fontName='Helvetica',
        fontSize=10.5,
        textColor=DARK,
        spaceAfter=3,
        leading=15,
        leftIndent=16,
        bulletIndent=4,
    )
    styles['url'] = ParagraphStyle(
        'T4LURL',
        fontName='Helvetica-Oblique',
        fontSize=10,
        textColor=GRAY,
        spaceAfter=6,
        leading=14,
    )
    styles['page_num'] = ParagraphStyle(
        'T4LPageNum',
        fontName='Helvetica',
        fontSize=9,
        textColor=GRAY,
        alignment=TA_CENTER,
    )

    # Script-specific
    styles['segment_header'] = ParagraphStyle(
        'T4LSegmentHeader',
        fontName='Helvetica-Bold',
        fontSize=13,
        textColor=RED,
        spaceBefore=20,
        spaceAfter=4,
        leading=18,
    )
    styles['label'] = ParagraphStyle(
        'T4LLabel',
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=GRAY,
        spaceAfter=2,
        leading=14,
    )
    styles['narration'] = ParagraphStyle(
        'T4LNarration',
        fontName='Helvetica-Oblique',
        fontSize=10.5,
        textColor=DARK,
        spaceAfter=5,
        leading=16,
        leftIndent=12,
        rightIndent=12,
    )
    styles['note'] = ParagraphStyle(
        'T4LNote',
        fontName='Helvetica-Oblique',
        fontSize=10,
        textColor=GRAY,
        spaceAfter=4,
        leading=14,
        leftIndent=12,
    )

    return styles


def divider():
    return HRFlowable(width='100%', thickness=1, color=RED, spaceAfter=8, spaceBefore=2)


def thin_divider():
    return HRFlowable(width='100%', thickness=0.5, color=MID_GRAY, spaceAfter=6, spaceBefore=4)


def page_number_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 9)
    canvas.setFillColor(GRAY)
    canvas.drawCentredString(
        doc.pagesize[0] / 2.0,
        0.45 * inch,
        f'Train4Life Admin — Page {doc.page}'
    )
    # top thin red bar
    canvas.setStrokeColor(RED)
    canvas.setLineWidth(2)
    canvas.line(0.75 * inch, doc.pagesize[1] - 0.5 * inch,
                doc.pagesize[0] - 0.75 * inch, doc.pagesize[1] - 0.5 * inch)
    canvas.restoreState()


def make_doc(path):
    return SimpleDocTemplate(
        path,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )


def bullets(items, styles):
    """Return a list of bullet Paragraphs."""
    return [Paragraph(f'\u2022  {item}', styles['bullet']) for item in items]


def section(title, url_hint, content_flowables, styles):
    """Return a list of flowables for one section."""
    items = []
    items.append(Paragraph(title, styles['section_header']))
    items.append(divider())
    if url_hint:
        items.append(Paragraph(url_hint, styles['url']))
    items.extend(content_flowables)
    return items


# ══════════════════════════════════════════════════════════════════════════════
#  PDF 1 — Complete Guide
# ══════════════════════════════════════════════════════════════════════════════

def build_guide():
    S = build_styles()
    doc = make_doc(GUIDE_PATH)
    story = []

    # ── Title page ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 1.4 * inch))
    story.append(Paragraph('TRAIN4LIFE', S['title']))
    story.append(Paragraph('ADMIN GUIDE', S['title']))
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph('Complete Reference for Managing train4life.life', S['subtitle']))
    story.append(Spacer(1, 0.3 * inch))
    # Confidential badge via a single-cell table
    badge_table = Table(
        [['  CONFIDENTIAL — ADMIN ONLY  ']],
        colWidths=[3 * inch],
    )
    badge_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), RED),
        ('TEXTCOLOR', (0, 0), (-1, -1), WHITE),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))

    # Center the badge
    story.append(Table(
        [[badge_table]],
        colWidths=[7 * inch],
        style=TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]),
    ))

    story.append(Spacer(1, 0.25 * inch))
    story.append(Paragraph('Generated April 2026', S['body_gray']))
    story.append(PageBreak())

    # ── Section 1 — Dashboard Overview ───────────────────────────────────────
    story += section(
        'SECTION 1 — DASHBOARD OVERVIEW',
        'URL: /admin/dashboard',
        [
            Paragraph(
                'The Dashboard is the home base for admin operations. It provides an at-a-glance view of '
                'the platform\'s health and quick navigation to every major section.',
                S['body']
            ),
            Paragraph('Stat Cards', S['subsection']),
        ] + bullets([
            'Revenue (MRR) — monthly recurring revenue pulled live from Stripe',
            'Subscribers — total count of active members',
            'App Videos — number of videos currently in the iOS app',
            'Total Videos — all content across both categories',
        ], S) + [
            Paragraph('Live Status Bar', S['subsection']),
            Paragraph(
                'Shows the current broadcast status: Off Air, Countdown, or Live. '
                'A Change link opens the Live Controls page.',
                S['body']
            ),
            Paragraph('Quick Nav Cards', S['subsection']),
        ] + bullets([
            'Live Controls — manage broadcast status and WebRTC streaming',
            'App Content — curate the iOS app video playlists',
            'Resources / PDFs — upload study guides for subscribers',
            'Messages — real-time direct messaging with members',
            'Members — subscriber list with Stripe details',
            'View Site — opens train4life.life in a new tab',
        ], S),
        S
    )

    story.append(Spacer(1, 0.2 * inch))

    # ── Section 2 — Managing Members ─────────────────────────────────────────
    story += section(
        'SECTION 2 — MANAGING MEMBERS',
        'URL: /admin/members',
        [
            Paragraph(
                'The Members page lists every subscriber with their account details.',
                S['body']
            ),
            Paragraph('Member List Columns', S['subsection']),
        ] + bullets([
            'Email address',
            'Display name',
            'Subscription status (active / cancelled / past_due)',
            'Account created date',
            'Stripe customer ID',
        ], S) + [
            Paragraph('Actions per Member', S['subsection']),
        ] + bullets([
            'DM — opens a direct message conversation with that member',
            'View — opens the member\'s account profile',
        ], S),
        S
    )

    # ── Section 3 — Messages & DMs ────────────────────────────────────────────
    story += section(
        'SECTION 3 — MESSAGES & DIRECT MESSAGES',
        'URL: /admin/messages  |  /admin/messages/dm/<email>',
        [
            Paragraph(
                'The Messages section provides real-time two-way communication with subscribers.',
                S['body']
            ),
            Paragraph('Features', S['subsection']),
        ] + bullets([
            'Message list — all conversations sorted by most recent activity',
            'DM thread — full conversation history with a single member',
            'Send a message — type in the input box and press Send or Enter',
            'Real-time delivery via Socket.IO — no page refresh required',
            'Message toast — pop-up notification (top-right) when a member sends a new DM',
            'Mini chat popup (bottom-right) — floating chat window, opens from the toast Reply button',
        ], S) + [
            Paragraph('Message Toast Buttons', S['subsection']),
        ] + bullets([
            'Reply — opens the mini chat popup for a quick response without leaving the current page',
            'Dismiss — closes the toast; the conversation remains unread in /admin/messages',
        ], S),
        S
    )

    story.append(PageBreak())

    # ── Section 4 — Video Calls ───────────────────────────────────────────────
    story += section(
        'SECTION 4 — VIDEO CALLS',
        None,
        [
            Paragraph(
                'Train4Life supports one-on-one WebRTC video calls between Jeff and any subscriber.',
                S['body']
            ),
            Paragraph('Call Flow', S['subsection']),
        ] + bullets([
            'A member initiates a call from their account page on the website',
            'Jeff receives an incoming call toast notification on any admin page',
            'The toast displays the caller\'s name with Accept and Decline buttons',
            'Accepting — navigates to the video call page; both parties connect via WebRTC',
            'Declining — dismisses the notification with no further action required',
        ], S),
        S
    )

    # ── Section 5 — Live Controls ─────────────────────────────────────────────
    story += section(
        'SECTION 5 — LIVE CONTROLS',
        'URL: /admin/live',
        [
            Paragraph(
                'Live Controls determines what visitors see on the Train4Life TV section of the website '
                'and manages the WebRTC broadcast.',
                S['body']
            ),
            Paragraph('Status Options', S['subsection']),
        ] + bullets([
            'Off Air — site shows no active stream',
            'Countdown — site displays a live countdown timer to build anticipation',
            'Live — site shows the active broadcast player',
        ], S) + [
            Paragraph('Countdown Settings', S['subsection']),
        ] + bullets([
            'Target date/time — pick when the countdown expires',
            'Timer target — Express, Bible Bootcamp, or Both',
            'Custom message — optional text shown alongside the countdown',
        ], S) + [
            Paragraph('WebRTC Broadcast', S['subsection']),
        ] + bullets([
            'Click GO LIVE to start broadcasting camera and microphone from the browser',
            'Viewer badge shows the number of people currently watching',
            'Click Stop to end the broadcast',
            'Changes take effect immediately for all website visitors',
        ], S),
        S
    )

    story.append(PageBreak())

    # ── Section 6 — App Content ───────────────────────────────────────────────
    story += section(
        'SECTION 6 — APP CONTENT MANAGEMENT',
        'URL: /admin/app-content',
        [
            Paragraph(
                'App Content controls the video playlists subscribers see inside the Train4Life iOS app.',
                S['body']
            ),
            Paragraph('Two Sections', S['subsection']),
        ] + bullets([
            'EXPRESS (red) — Express workout video series',
            'BIBLE BOOTCAMP (purple) — Bible Bootcamp video series',
        ], S) + [
            Paragraph('Adding a Video', S['subsection']),
        ] + bullets([
            'Paste the VHX video ID',
            'Enter the video title',
            'Optionally add a thumbnail URL',
            'Optionally add the VHX watch URL',
            'Click Add — the video appears in the app immediately',
        ], S) + [
            Paragraph('Managing Videos', S['subsection']),
        ] + bullets([
            'Each card shows the title, thumbnail preview, and a Remove button',
            'Drag and drop cards to reorder the playlist',
            'Remove deletes the video from the app playlist (the video remains on VHX)',
            'Subscribers see updated playlists on next app refresh',
        ], S),
        S
    )

    # ── Section 7 — PDFs ─────────────────────────────────────────────────────
    story += section(
        'SECTION 7 — PDFs SECTION',
        'URL: /admin/pdfs',
        [
            Paragraph(
                'Upload and manage PDF study guides that subscribers can access from their dashboard.',
                S['body']
            ),
            Paragraph('Uploading a PDF', S['subsection']),
        ] + bullets([
            'Choose the PDF file from your local machine',
            'Enter a title for the document',
            'Enter a short description',
            'Click Upload — the file is stored in static/pdfs/ and appears in the subscriber library',
        ], S) + [
            Paragraph('Managing PDFs', S['subsection']),
        ] + bullets([
            'Each uploaded PDF has a Delete button (requires confirmation)',
            'Subscribers access PDFs from their account dashboard on train4life.life',
        ], S),
        S
    )

    story.append(PageBreak())

    # ── Section 8 — Admin Guide ───────────────────────────────────────────────
    story += section(
        'SECTION 8 — ADMIN GUIDE SECTION',
        'URL: /admin/guide',
        [
            Paragraph(
                'The Guide page hosts this document — the built-in admin reference — rendered inline.',
                S['body']
            ),
        ] + bullets([
            'Inline PDF viewer — embedded at full height for easy reading without downloading',
            'Download PDF button — saves the guide locally',
            'This is the section you are reading right now',
        ], S),
        S
    )

    # ── Section 9 — Notifications & Toasts ───────────────────────────────────
    story += section(
        'SECTION 9 — NOTIFICATIONS & TOASTS',
        None,
        [
            Paragraph(
                'Jeff receives real-time notifications on every admin page that extends admin_base.html.',
                S['body']
            ),
            Paragraph('Message Toast (top-right, dark popup)', S['subsection']),
        ] + bullets([
            'Triggers when a member sends a new direct message',
            'Shows the member\'s name and a message preview',
            'Reply button — opens the mini chat popup for an immediate response',
            'Dismiss button — closes the toast without responding',
        ], S) + [
            Paragraph('Call Toast (top-center, red border)', S['subsection']),
        ] + bullets([
            'Triggers when a member initiates a video call',
            'Shows the caller\'s name',
            'Accept — navigates to the video call page',
            'Decline — dismisses the notification',
        ], S) + [
            Paragraph('Mini Chat Popup (bottom-right)', S['subsection']),
        ] + bullets([
            'Floating chat window with the full DM thread',
            'Opens automatically when Reply is clicked on a message toast',
            'Includes a full-view link to navigate to the complete DM thread',
        ], S),
        S
    )

    story.append(PageBreak())

    # ── Section 10 — Stripe ───────────────────────────────────────────────────
    story += section(
        'SECTION 10 — STRIPE SUBSCRIPTIONS',
        None,
        [
            Paragraph(
                'Stripe manages all billing, subscription lifecycle, and revenue reporting for Train4Life.',
                S['body']
            ),
            Paragraph('Webhook Integration', S['subsection']),
        ] + bullets([
            'Webhook endpoint listens for Stripe events (checkout completed, subscription updated, cancelled)',
            'New subscribers: webhook creates a user record and grants platform access',
            'Cancelled subscriptions: access is revoked at the end of the billing period',
            'Webhook secret: configured as STRIPE_WEBHOOK_SECRET environment variable on Render',
        ], S) + [
            Paragraph('Revenue & Billing', S['subsection']),
        ] + bullets([
            'MRR stat on the Dashboard is pulled live from the Stripe API',
            'Subscribers manage their own billing at /portal (Stripe-hosted customer portal)',
        ], S),
        S
    )

    # ── Build ──────────────────────────────────────────────────────────────────
    doc.build(story, onFirstPage=page_number_footer, onLaterPages=page_number_footer)
    print(f'Guide PDF written to {GUIDE_PATH}')


# ══════════════════════════════════════════════════════════════════════════════
#  PDF 2 — Walkthrough Script
# ══════════════════════════════════════════════════════════════════════════════

def segment(number, title, timing, screen, narration, note, styles):
    """Return a list of flowables for one script segment."""
    items = []

    header_text = f'SEGMENT {number} — {title}  <font color="#71717a" size="10">({timing})</font>'
    items.append(Paragraph(header_text, styles['segment_header']))
    items.append(divider())

    # Screen row
    screen_table = Table(
        [
            [Paragraph('SCREEN:', styles['label']),
             Paragraph(screen, styles['body'])],
        ],
        colWidths=[0.85 * inch, 6.15 * inch],
        style=TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]),
    )
    items.append(screen_table)
    items.append(Spacer(1, 0.06 * inch))

    # Narration box
    items.append(Paragraph('NARRATION:', styles['label']))
    narration_table = Table(
        [[Paragraph(f'"{narration}"', styles['narration'])]],
        colWidths=[7 * inch],
        style=TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), LIGHT_GRAY),
            ('BOX', (0, 0), (-1, -1), 1, MID_GRAY),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]),
    )
    items.append(narration_table)

    if note:
        items.append(Spacer(1, 0.04 * inch))
        items.append(Paragraph(f'[NOTE] {note}', styles['note']))

    items.append(Spacer(1, 0.1 * inch))
    return items


def build_script():
    S = build_styles()
    doc = make_doc(SCRIPT_PATH)
    story = []

    # ── Title page ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 1.2 * inch))
    story.append(Paragraph('TRAIN4LIFE ADMIN', S['title']))
    story.append(Paragraph('WALKTHROUGH SCRIPT', S['title']))
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph('Video Recording Script — ~15 Minutes', S['subtitle']))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph('Jeff Ratliff — Internal Use Only', S['subtitle']))
    story.append(Spacer(1, 0.35 * inch))

    meta_data = [
        ['Presenter:', 'Jeff Ratliff'],
        ['Duration:', '~15 minutes'],
        ['Audience:', 'Internal — Admin Only'],
        ['Purpose:', 'Walkthrough recording of the Train4Life admin panel'],
    ]
    meta_table = Table(
        meta_data,
        colWidths=[1.3 * inch, 4.5 * inch],
        style=TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10.5),
            ('TEXTCOLOR', (0, 0), (0, -1), GRAY),
            ('TEXTCOLOR', (1, 0), (1, -1), DARK),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LINEBELOW', (0, -1), (-1, -1), 0.5, MID_GRAY),
        ]),
    )
    story.append(Table(
        [[meta_table]],
        colWidths=[7 * inch],
        style=TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]),
    ))
    story.append(PageBreak())

    # ── Segment 1 — Intro ─────────────────────────────────────────────────────
    story += segment(
        1, 'INTRO', '0:00–0:45',
        screen='Admin login page, then Dashboard',
        narration=(
            "Welcome to the Train4Life admin panel — this is the control center for everything on "
            "train4life.life. Today I'm walking through every feature so you know exactly where to go "
            "and what to do. Let's start on the Dashboard."
        ),
        note='Log in before recording. Have real subscriber data visible.',
        styles=S,
    )

    # ── Segment 2 — Dashboard ─────────────────────────────────────────────────
    story += segment(
        2, 'DASHBOARD', '0:45–2:00',
        screen='/admin/dashboard — scroll through all stat cards and nav cards',
        narration=(
            "The Dashboard shows your key metrics at a glance — revenue, subscriber count, app video "
            "count, and total videos. Below that is the live status bar — right now we're Off Air. "
            "I can click Change to update that. And here are the quick links to all the major sections "
            "— Live Controls, App Content, Resources, Messages, and Members."
        ),
        note='Point to each stat card as you name it.',
        styles=S,
    )

    # ── Segment 3 — Live Controls ─────────────────────────────────────────────
    story += segment(
        3, 'LIVE CONTROLS', '2:00–4:30',
        screen='/admin/live — click through status options, show countdown timer',
        narration=(
            "Live Controls is where I manage what members see on the website. I can set the status "
            "to Off Air, Countdown — which shows a timer to build anticipation — or Live when I'm "
            "actually streaming. I'll set it to Countdown and pick a time... now the website is "
            "showing a live countdown. When I'm ready to go live, I flip it to Live and hit Start "
            "Broadcasting to send my camera feed directly to Train4Life TV viewers."
        ),
        note='Actually change the status to Countdown during recording, then change back to Off Air after.',
        styles=S,
    )

    story.append(PageBreak())

    # ── Segment 4 — Members ───────────────────────────────────────────────────
    story += segment(
        4, 'MEMBERS', '4:30–5:30',
        screen='/admin/members — scroll through member list',
        narration=(
            "The Members page lists everyone who has an active subscription. I can see their email, "
            "when they joined, and their Stripe customer ID. From here I can jump directly into a DM "
            "conversation with any member by clicking the DM button."
        ),
        note=None,
        styles=S,
    )

    # ── Segment 5 — Messages ──────────────────────────────────────────────────
    story += segment(
        5, 'MESSAGES', '5:30–7:30',
        screen='/admin/messages — open a DM thread, send a test message',
        narration=(
            "The Messages section shows all my conversations with members. Each row is a member "
            "I've exchanged messages with. I'll click into this one... here's the full thread. "
            "I can type a reply right here and it sends in real time — no page refresh needed. "
            "Members receive the message instantly on their account page."
        ),
        note='Send a real test message to yourself if possible.',
        styles=S,
    )

    # ── Segment 6 — Notifications Demo ───────────────────────────────────────
    story += segment(
        6, 'NOTIFICATIONS DEMO', '7:30–9:00',
        screen='Any admin page — trigger a message notification from another browser/device',
        narration=(
            "One of the best features is the real-time notification system. When a member sends me "
            "a message, this toast appears — it shows their name and a preview of the message. "
            "I can click Reply to open a mini chat popup right here without leaving the page, or "
            "Dismiss if I'll get back to it later. If a member calls me for a video chat, I get a "
            "call notification with Accept and Decline buttons."
        ),
        note='Have someone send a test message to trigger the live toast.',
        styles=S,
    )

    story.append(PageBreak())

    # ── Segment 7 — App Content ───────────────────────────────────────────────
    story += segment(
        7, 'APP CONTENT', '9:00–11:00',
        screen='/admin/app-content — show both sections, add and remove a video',
        narration=(
            "App Content controls what subscribers see in the Train4Life iOS app. There are two "
            "sections — Express on the red side, and Bible Bootcamp on the purple side. To add a "
            "video, I paste the VHX video ID and title here... and hit Add. It immediately appears "
            "in the app. I can drag cards to reorder them. Remove removes it from the app — but the "
            "video stays on VHX."
        ),
        note=None,
        styles=S,
    )

    # ── Segment 8 — PDFs ─────────────────────────────────────────────────────
    story += segment(
        8, 'PDFs', '11:00–12:00',
        screen='/admin/pdfs — upload a PDF',
        narration=(
            "The PDFs section lets me upload study guides and resources for subscribers. I give it "
            "a title, a description, choose the file, and click Upload. It appears in the subscriber "
            "PDF library right away. I can delete any PDF with the Delete button."
        ),
        note=None,
        styles=S,
    )

    # ── Segment 9 — Wrap Up ───────────────────────────────────────────────────
    story += segment(
        9, 'WRAP UP', '12:00–13:00',
        screen='Dashboard',
        narration=(
            "That covers the full Train4Life admin panel — Dashboard for your overview, Live Controls "
            "to manage your broadcast status, Members to see your subscribers, Messages for real-time "
            "DMs, App Content to curate the iOS app, and PDFs for study materials. The notification "
            "system keeps you connected to members no matter which page you're on. If you have "
            "questions, check the Admin Guide PDF on the Guide page."
        ),
        note='End on Dashboard. Keep the recording under 15 minutes.',
        styles=S,
    )

    # ── Build ──────────────────────────────────────────────────────────────────
    doc.build(story, onFirstPage=page_number_footer, onLaterPages=page_number_footer)
    print(f'Script PDF written to {SCRIPT_PATH}')


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    build_guide()
    build_script()
    print('Done.')
