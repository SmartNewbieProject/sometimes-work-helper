# from apscheduler.schedulers.background import BackgroundScheduler
# import logging
# from .slack_client import SlackClient
# from .message_processor import MessageProcessor, extract_ticket_candidates

# logger = logging.getLogger(__name__)

# slack = SlackClient()
# processor = MessageProcessor()

# scheduler = BackgroundScheduler()

# def scheduled_message_processing():
#     messages = slack.get_recent_messages(minutes=120)
#     new_messages = processor.filter_new_messages(messages)
#     if not new_messages:
#         logger.info("No new messages to process.")
#         return
#     candidates = extract_ticket_candidates(new_messages)
#     logger.info(f"티켓 후보: {candidates}")
#     for candidate in candidates:
#         if candidate.get('is_duplicate'):
#             logger.info(f"중복 티켓으로 판단되어 생성하지 않음: {candidate.get('duplicate_reason', '')}")
#             continue
#         orig = next((m for m in new_messages if m.get('_hash') == candidate.get('_hash')), None)
#         logger.info(f"send_approval_message 호출 전: {candidate}")
#         result = slack.send_approval_message(candidate['ticket_info'], orig)
#         logger.info(f"send_approval_message 호출 후: {result}")
#         if orig:
#             processor.mark_message_processed(orig['_hash'], orig)

# scheduler.add_job(scheduled_message_processing, 'interval', minutes=1)  

# def start_scheduler():
#     scheduler.start() 