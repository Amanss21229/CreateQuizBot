"""
Bilingual message system — English (en) and Hindi (hi).
Usage:  from lang import t
        t('key', lang, kwarg=value)
"""

MESSAGES = {
    'en': {
        # ── Inactive bot ─────────────────────────────────────────────────────
        'inactive_title': '🔴 <b>Bot is Not Active</b>',
        'inactive_body':  'This bot is currently inactive.\nPlease contact the owner for help.',
        'inactive_btn':   '📩 Contact Owner',

        # ── Force join ───────────────────────────────────────────────────────
        'force_join_title': '⛔ <b>Access Restricted!</b>',
        'force_join_body':  'You must join our channel/group to use this bot.\n\n'
                            '👇 Click the button below to join, then try again.',
        'force_join_btn':   '📢 Join Channel / Group',

        # ── Group added ──────────────────────────────────────────────────────
        'group_added': '👋 <b>Thanks for adding me!</b>\n\n'
                       "I'm a Quiz Bot. The bot owner will send quizzes here automatically. "
                       'Use /leaderboard to see rankings!',

        # ── Leaderboard ──────────────────────────────────────────────────────
        'lb_group_header':        '🏆 <b>Leaderboard — {chat_link}</b>\n📅 <i>{date}</i>\n',
        'lb_global_header':       '🌍 <b>Global Leaderboard (Top {limit})</b>\n📅 <i>{date}</i>\n',
        'lb_daily_group_header':  '🏆 <b>Daily Leaderboard — {chat_link}</b>\n📅 <i>{date}</i>\n',
        'lb_daily_global_header': '🌍 <b>Global Leaderboard — Top {limit}</b>\n📅 <i>{date}</i>\n',
        'lb_no_attempts':         '📊 No quiz attempts yet in this group!',
        'lb_no_attempts_global':  '📊 No quiz attempts yet!',
        'lb_no_attempts_daily':   'No attempts yet!',
        'lb_row':         '{rank} {name}\n   ✅ {correct} correct | ❌ {wrong} wrong | '
                          '📝 {attempted} attempted | 🏅 {marks} pts\n\n',
        'lb_row_compact': '{rank} {name} | ✅{correct} ❌{wrong} 🏅{marks}pts\n',
        'lb_global_row':  '{rank} {name} — 🏅 {marks} pts\n',

        # ── myRank ───────────────────────────────────────────────────────────
        'myrank_header':         '📊 <b>Your Rankings</b>\n\n',
        'myrank_group_section':  '🏘️ <b>In {group}:</b>\n',
        'myrank_global_section': '🌍 <b>Global:</b>\n',
        'myrank_global_header':  '🌍 <b>Your Global Rank</b>\n\n',
        'myrank_rank':           '  🏆 Rank: #{rank} out of {total}\n',
        'myrank_correct':        '  ✅ Correct: {n}\n',
        'myrank_wrong':          '  ❌ Wrong: {n}\n',
        'myrank_attempted':      '  📝 Attempted: {n}\n',
        'myrank_marks':          '  🏅 Total Marks: {n}\n',
        'myrank_no_group':       '  No attempts yet in this group.\n\n',
        'myrank_no_global':      '  No global attempts yet.\n',
        'myrank_no_attempts':    "You haven't attempted any quizzes yet!",

        # ── /language command ────────────────────────────────────────────────
        'language_title':        '🌐 <b>Bot Language Settings</b>',
        'language_body':         'Choose the language for this bot.\n\n'
                                 '• <b>English</b> — All messages in English, quizzes sent as-is\n'
                                 '• <b>Hindi</b> — All messages in Hindi, quizzes auto-translated to Hindi',
        'language_current_en':   '✅ Currently set to: <b>English 🇬🇧</b>',
        'language_current_hi':   '✅ Currently set to: <b>Hindi 🇮🇳</b>',
        'language_set_en':       '✅ <b>Language set to English!</b>\nAll bot messages will now be in English.',
        'language_set_hi':       '✅ <b>Language set to Hindi!</b>\n'
                                 'Sab messages Hindi mein aayenge aur quizzes bhi Hindi mein translate honge. 🇮🇳',
        'language_btn_en':       '🇬🇧 English',
        'language_btn_hi':       '🇮🇳 Hindi',
        'language_no_permission': '⛔ Only group admins, bot owner, or main admin can change the language.',

        # ── Quiz distribution ────────────────────────────────────────────────
        'translating':       '🔄 Translating quiz to Hindi…',
        'translation_done':  '✅ Quiz translated to Hindi!',
        'translation_failed':'⚠️ Translation failed, sending original.',
    },

    'hi': {
        # ── Inactive bot ─────────────────────────────────────────────────────
        'inactive_title': '🔴 <b>बॉट अभी सक्रिय नहीं है</b>',
        'inactive_body':  'यह बॉट फ़िलहाल निष्क्रिय है।\nमदद के लिए कृपया मालिक से संपर्क करें।',
        'inactive_btn':   '📩 मालिक से संपर्क करें',

        # ── Force join ───────────────────────────────────────────────────────
        'force_join_title': '⛔ <b>पहुँच प्रतिबंधित!</b>',
        'force_join_body':  'इस बॉट का उपयोग करने के लिए आपको हमारे चैनल/ग्रुप से जुड़ना होगा।\n\n'
                            '👇 नीचे बटन दबाएं, जुड़ें, फिर दोबारा कोशिश करें।',
        'force_join_btn':   '📢 चैनल / ग्रुप जॉइन करें',

        # ── Group added ──────────────────────────────────────────────────────
        'group_added': '👋 <b>मुझे जोड़ने के लिए शुक्रिया!</b>\n\n'
                       'मैं एक क्विज़ बॉट हूँ। बॉट का मालिक यहाँ क्विज़ भेजेगा। '
                       'रैंकिंग देखने के लिए /leaderboard टाइप करें!',

        # ── Leaderboard ──────────────────────────────────────────────────────
        'lb_group_header':        '🏆 <b>लीडरबोर्ड — {chat_link}</b>\n📅 <i>{date}</i>\n',
        'lb_global_header':       '🌍 <b>ग्लोबल लीडरबोर्ड (टॉप {limit})</b>\n📅 <i>{date}</i>\n',
        'lb_daily_group_header':  '🏆 <b>आज का लीडरबोर्ड — {chat_link}</b>\n📅 <i>{date}</i>\n',
        'lb_daily_global_header': '🌍 <b>ग्लोबल लीडरबोर्ड — टॉप {limit}</b>\n📅 <i>{date}</i>\n',
        'lb_no_attempts':         '📊 इस ग्रुप में अभी तक कोई क्विज़ प्रयास नहीं हुआ!',
        'lb_no_attempts_global':  '📊 अभी तक कोई क्विज़ प्रयास नहीं हुआ!',
        'lb_no_attempts_daily':   'अभी तक कोई प्रयास नहीं!',
        'lb_row':         '{rank} {name}\n   ✅ {correct} सही | ❌ {wrong} गलत | '
                          '📝 {attempted} कोशिश | 🏅 {marks} अंक\n\n',
        'lb_row_compact': '{rank} {name} | ✅{correct} ❌{wrong} 🏅{marks}अंक\n',
        'lb_global_row':  '{rank} {name} — 🏅 {marks} अंक\n',

        # ── myRank ───────────────────────────────────────────────────────────
        'myrank_header':         '📊 <b>आपकी रैंकिंग</b>\n\n',
        'myrank_group_section':  '🏘️ <b>{group} में:</b>\n',
        'myrank_global_section': '🌍 <b>ग्लोबल:</b>\n',
        'myrank_global_header':  '🌍 <b>आपकी ग्लोबल रैंक</b>\n\n',
        'myrank_rank':           '  🏆 रैंक: #{rank} में से {total}\n',
        'myrank_correct':        '  ✅ सही: {n}\n',
        'myrank_wrong':          '  ❌ गलत: {n}\n',
        'myrank_attempted':      '  📝 कोशिश: {n}\n',
        'myrank_marks':          '  🏅 कुल अंक: {n}\n',
        'myrank_no_group':       '  इस ग्रुप में अभी तक कोई प्रयास नहीं।\n\n',
        'myrank_no_global':      '  ग्लोबल में अभी तक कोई प्रयास नहीं।\n',
        'myrank_no_attempts':    'आपने अभी तक कोई क्विज़ नहीं खेला!',

        # ── /language command ────────────────────────────────────────────────
        'language_title':        '🌐 <b>बॉट भाषा सेटिंग</b>',
        'language_body':         'इस बॉट की भाषा चुनें।\n\n'
                                 '• <b>English</b> — सभी संदेश अंग्रेज़ी में, क्विज़ जैसे हैं वैसे\n'
                                 '• <b>हिंदी</b> — सभी संदेश हिंदी में, क्विज़ भी हिंदी में अनुवाद होंगे',
        'language_current_en':   '✅ अभी सेट है: <b>English 🇬🇧</b>',
        'language_current_hi':   '✅ अभी सेट है: <b>हिंदी 🇮🇳</b>',
        'language_set_en':       '✅ <b>Language set to English!</b>\nAll bot messages will now be in English.',
        'language_set_hi':       '✅ <b>भाषा हिंदी में सेट हो गई!</b>\n'
                                 'सभी संदेश हिंदी में आएंगे और क्विज़ भी हिंदी में अनुवाद होंगे। 🇮🇳',
        'language_btn_en':       '🇬🇧 English',
        'language_btn_hi':       '🇮🇳 हिंदी',
        'language_no_permission': '⛔ केवल ग्रुप एडमिन, बॉट मालिक या मेन एडमिन ही भाषा बदल सकते हैं।',

        # ── Quiz distribution ────────────────────────────────────────────────
        'translating':       '🔄 क्विज़ हिंदी में अनुवाद हो रहा है…',
        'translation_done':  '✅ क्विज़ हिंदी में अनुवाद हो गया!',
        'translation_failed':'⚠️ अनुवाद विफल, मूल भाषा में भेजा जा रहा है।',
    },
}


def t(key: str, lang: str = 'en', **kwargs) -> str:
    """Return a translated string, falling back to English if key missing in target lang."""
    lang = lang if lang in MESSAGES else 'en'
    msg = MESSAGES[lang].get(key) or MESSAGES['en'].get(key, key)
    if kwargs:
        try:
            return msg.format(**kwargs)
        except (KeyError, IndexError):
            return msg
    return msg
