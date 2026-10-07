# Graph Report - .  (2026-10-01)

## Corpus Check
- 50 files · ~59,052 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 664 nodes · 1540 edges · 42 communities
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 68 edges (avg confidence: 0.77)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Module 0
- Module 1
- Module 2
- Module 3
- Module 4
- Module 5
- Module 6
- Module 7
- Module 8
- Module 9
- Module 10
- Module 11
- Module 12
- Module 13
- Module 15
- Module 16
- Module 17
- Module 18
- Module 19
- Module 20
- Module 21
- Module 22
- Module 23
- Module 24
- Module 25
- Module 26
- Module 27
- Module 28
- Module 29
- Module 30
- Module 31
- Module 32
- Module 33
- Module 34
- Module 35

## God Nodes (most connected - your core abstractions)
1. `get_msg()` - 34 edges
2. `run_topic_mirror()` - 33 edges
3. `get_data()` - 23 edges
4. `chk_mirror_user()` - 22 edges
5. `copy_message_with_chat_id()` - 21 edges
6. `format_caption_to_html()` - 18 edges
7. `upload_media()` - 18 edges
8. `transfer_single_message()` - 18 edges
9. `chk_user()` - 16 edges
10. `smart_broadcast_callback()` - 16 edges

## Surprising Connections (you probably didn't know these)
- `get_all_target_forum_topics()` --indirect_call--> `date()`  [INFERRED]
  toxic/modules/topic_mirror.py → Youtube/date.py
- `song_search()` --indirect_call--> `executor()`  [INFERRED]
  Youtube/song_search.py → toxic/modules/eval.py
- `download_music()` --indirect_call--> `executor()`  [INFERRED]
  Youtube/song_search.py → toxic/modules/eval.py
- `schedule_broadcast_task()` --calls--> `get_client()`  [INFERRED]
  toxic/__main__.py → toxic/__init__.py
- `delete_all_active_broadcast_messages()` --calls--> `get_client()`  [INFERRED]
  toxic/modules/broadcast.py → toxic/__init__.py

## Import Cycles
- 1-file cycle: `toxic/core/toxictools.py -> toxic/core/toxictools.py`

## Communities (42 total, 0 thin omitted)

### Community 0 - "Module 0"
Cohesion: 0.06
Nodes (87): TelegramClient, add_pdf_watermark(), progress_bar(), screenshot(), thumbnail(), video_metadata(), add_user_custom_tag(), apply_custom_caption_placeholders() (+79 more)

### Community 1 - "Module 1"
Cohesion: 0.05
Nodes (69): get_seconds(), ban_user(), is_user_banned(), unban_user(), add_mirror_premium(), add_premium(), add_toxic_id(), check_mirror_premium() (+61 more)

### Community 2 - "Module 2"
Cohesion: 0.06
Nodes (61): add_auth_channel(), add_forward_mapping(), all_words_remove(), clean_words(), delete_session(), get_all_forward_mappings(), get_auth_channels(), get_data() (+53 more)

### Community 3 - "Module 3"
Cohesion: 0.09
Nodes (53): add_broadcast_deletion(), add_joined_chat(), get_all_joined_chats(), get_broadcast_config(), get_custom_group_bio(), get_pending_deletions(), load_all_thumbnails(), Retrieves configured global group bio/description from MongoDB, or default. (+45 more)

### Community 4 - "Module 4"
Cohesion: 0.10
Nodes (30): chk_user(), gen_link(), get_link(), hhmmss(), _opencv_worker(), userbot_join(), get_client(), delete_all_callback() (+22 more)

### Community 5 - "Module 5"
Cohesion: 0.10
Nodes (29): about_disabled(), ai_soon(), cancel(), converter_soon(), dev_soon(), help_soon(), music_soon(), CallbackQuery (+21 more)

### Community 6 - "Module 6"
Cohesion: 0.10
Nodes (26): InlineKeyboardMarkup, subscribe(), build_keyboard(), generate_random_param(), Message, Generate a random parameter., Handle the /start command., sharelink_handler() (+18 more)

### Community 7 - "Module 7"
Cohesion: 0.17
Nodes (29): add_sb_deletion(), add_sb_destination(), delete_all_active_sb_messages(), execute_smart_broadcast_round(), format_time_duration(), get_pending_sb_deletions(), get_sb_config(), get_sb_delete_timer_keyboard() (+21 more)

### Community 8 - "Module 8"
Cohesion: 0.15
Nodes (17): fast_download(), fast_upload(), convert(), optimize_thumbnail(), save_thumbnail(), Timer, d_thumbnail(), direct_link_downloader() (+9 more)

### Community 9 - "Module 9"
Cohesion: 0.12
Nodes (20): humanbytes(), prog_bar(), TimeFormatter(), Updates the highest message ID copied for a topic., update_mirror_topic_checkpoint(), do_reupload_topic_callback(), ensure_userbot_connected(), extract_caption_content_ids() (+12 more)

### Community 10 - "Module 10"
Cohesion: 0.19
Nodes (16): chk_mirror_user(), Checks if a user has active Topic Mirroring plan (or is Owner/Sudo). Returns 0 i, cancel_mirror_callback(), do_single_topic_callback(), get_working_userbot(), pick_single_topic_callback(), CallbackQuery, Interactive prompt flow for mirroring from ONE specific topic link to ANOTHER to (+8 more)

### Community 11 - "Module 11"
Cohesion: 0.19
Nodes (10): aexec(), edit_or_reply(), executor(), shellrunner(), auto_react(), download_music(), format_duration(), CallbackQuery (+2 more)

### Community 12 - "Module 12"
Cohesion: 0.17
Nodes (10): auto_delete_group_service_messages(), clean_topic_title(), is_media_type_enabled(), parse_topic_link(), Auto-deletes all group service messages:     - New Member Join / Leave notifica, Checks if the user has enabled or disabled this specific media filter in /settin, Parses a Telegram topic link to extract (chat_id, topic_id).     Supports:, Cleans topic title by removing leading diamond emoji prefixes or clutter, preser (+2 more)

### Community 13 - "Module 13"
Cohesion: 0.27
Nodes (10): delete_mirror_session(), get_user_mirror_sessions(), Retrieves all saved mirror sessions for a user, sorted by last updated., Deletes a saved mirror session., back_to_hub_callback(), build_mirror_hub_keyboard(), clear_sessions_callback(), delete_single_session_callback() (+2 more)

### Community 15 - "Module 15"
Cohesion: 0.36
Nodes (9): build_speedtest_report(), get_readable_file_size(), get_readable_time(), pyrogram_speedtest_cmd(), Converts bits per second to human-readable Mbps and MB/s., Runs speedtest synchronously inside a worker thread to avoid blocking Pyrogram/T, run_speedtest_sync(), speed_convert() (+1 more)

### Community 16 - "Module 16"
Cohesion: 0.22
Nodes (9): alphanumeric_topic_title(), get_all_target_forum_topics(), match_existing_target_topic(), normalize_topic_title(), Normalizes topic title for robust matching across spaces, casing, emojis and pun, Extracts purely letters and numbers for fail-safe topic matching., Matches a source topic title against existing target topics using multi-level ma, Scans ALL existing forum topics in target supergroup using raw RPC GetForumTopic (+1 more)

### Community 17 - "Module 17"
Cohesion: 0.25
Nodes (7): buildpacks, description, logo, name, repository, stack, success_url

### Community 18 - "Module 18"
Cohesion: 0.29
Nodes (7): fetch_all_messages_for_topic(), get_highest_topic_checkpoint(), Scans source and target groups, compares total content per topic,     and retur, Finds the highest last_msg_id checkpoint for a source topic across ALL MongoDB s, Fetches all pending messages for a specific forum topic.     Returns messages s, scan_and_compare_session(), scan_session_callback()

### Community 19 - "Module 19"
Cohesion: 0.33
Nodes (6): keywords, MusicBot, pyrogram, python3, telegram, telegram-bot

### Community 20 - "Module 20"
Cohesion: 0.33
Nodes (6): get_mirror_session(), Retrieves saved topic mappings and progress for a source-target pair., build_session_action_keyboard(), edit_target_callback(), Builds action options for a selected saved mirror session., session_options_callback()

### Community 21 - "Module 21"
Cohesion: 0.40
Nodes (5): description, required, value, env, AD_API

### Community 22 - "Module 22"
Cohesion: 0.40
Nodes (5): new_mirror_callback(), parse_source_link(), Interactive flow to configure and launch a new topic mirror session., Parses various Telegram message link formats., start_new_mirror_flow()

### Community 23 - "Module 23"
Cohesion: 0.50
Nodes (4): description, required, value, API_HASH

### Community 24 - "Module 24"
Cohesion: 0.50
Nodes (4): description, required, value, API_ID

### Community 25 - "Module 25"
Cohesion: 0.50
Nodes (4): description, required, value, BOT_TOKEN

### Community 26 - "Module 26"
Cohesion: 0.50
Nodes (4): description, required, value, CHANNEL_ID

### Community 27 - "Module 27"
Cohesion: 0.50
Nodes (4): FREEMIUM_LIMIT, description, required, value

### Community 28 - "Module 28"
Cohesion: 0.50
Nodes (4): LOG_GROUP, description, required, value

### Community 29 - "Module 29"
Cohesion: 0.50
Nodes (4): MONGO_DB, description, required, value

### Community 30 - "Module 30"
Cohesion: 0.50
Nodes (4): OWNER_ID, description, required, value

### Community 31 - "Module 31"
Cohesion: 0.50
Nodes (4): PREMIUM_LIMIT, description, required, value

### Community 32 - "Module 32"
Cohesion: 0.50
Nodes (4): STRING, description, required, value

### Community 33 - "Module 33"
Cohesion: 0.50
Nodes (4): SUDO_USERS, description, required, value

### Community 34 - "Module 34"
Cohesion: 0.50
Nodes (4): WEBSITE_URL, description, required, value

### Community 35 - "Module 35"
Cohesion: 0.50
Nodes (3): download_song_callback(), CallbackQuery, Client

## Knowledge Gaps
- **51 isolated node(s):** `name`, `description`, `logo`, `python3`, `telegram` (+46 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run_topic_mirror()` connect `Module 9` to `Module 0`, `Module 2`, `Module 3`, `Module 6`, `Module 10`, `Module 12`, `Module 16`, `Module 18`, `Module 20`, `Module 22`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Why does `handle_force_subscribe()` connect `Module 5` to `Module 6`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Why does `handle_large_file()` connect `Module 0` to `Module 6`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Are the 48 inferred relationships involving `InlineKeyboardMarkup` (e.g. with `subscribe()` and `handle_large_file()`) actually correct?**
  _`InlineKeyboardMarkup` has 48 INFERRED edges - model-reasoned connections that need verification._
- **What connects `name`, `description`, `logo` to the rest of the system?**
  _51 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Module 0` be split into smaller, more focused modules?**
  _Cohesion score 0.056856187290969896 - nodes in this community are weakly interconnected._
- **Should `Module 1` be split into smaller, more focused modules?**
  _Cohesion score 0.05427905427905428 - nodes in this community are weakly interconnected._