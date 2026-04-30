#!/bin/bash
# Copy this file to run_bot.sh and fill in your real values
# run_bot.sh is gitignored so your tokens stay safe

export SLACK_BOT_TOKEN="xoxb-YOUR-TOKEN-HERE"
export SLACK_CHANNEL_ID="C-YOUR-CHANNEL-ID-HERE"

source /Users/YOUR_MAC_USERNAME/audition-bot-env/bin/activate
python3 /Users/YOUR_MAC_USERNAME/repos/audition-forum-bot-main/scrape_and_notify.py >> /Users/YOUR_MAC_USERNAME/repos/audition-forum-bot-main/bot.log 2>&1
