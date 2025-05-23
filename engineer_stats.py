import os
from dotenv import load_dotenv
import requests
from collections import defaultdict
from datetime import datetime, timedelta, time as dt_time

load_dotenv()


ZENDESK_EMAIL = os.getenv("ZENDESK_EMAIL")
ZENDESK_TOKEN = os.getenv("ZENDESK_TOKEN")
ZENDESK_DOMAIN = os.getenv("ZENDESK_DOMAIN")
headers = {
        "Content-Type": "application/json"
    }
SLACK_WEBHOOK_URL_EMEA = os.getenv("SLACK_WEBHOOK_URL_EMEA")
SLACK_WEBHOOK_URL_APAC = os.getenv("SLACK_WEBHOOK_URL_APAC")
SLACK_WEBHOOK_URL_US = os.getenv("SLACK_WEBHOOK_URL_US")

ZAPIER_WEBHOOK_URL = os.getenv("ZAPIER_WEBHOOK_URL")

AGENT_MAP = {
    "38816121716121": {"name": "Akriti Saxena", "slack" : "U07QNDMGG87", "shift": "APAC"},
    "32883524162969": {"name": "Aditya V Dhapte", "slack" : "U074QGXKM0U" ,"shift": "EMEA"},
    "30050297796633": {"name": "Smruthi Patgar", "slack" : "U06PXUMRCJW", "shift": "EMEA"},
    "25874930116633": {"name": "Shubham Singh", "slack" : "U067TGEFA1Y", "shift": "APAC"},
    "24453369793177": {"name": "Vedik Ramesh", "slack" : "U06294G1GBU", "shift": "EMEA"},
    "24367218021657": {"name": "Aravind S", "slack" : "U061PBYDVLM", "shift": "APAC"},
    "20667761359257": {"name": "Ankita Pradhan", "slack" : "U05GPEQRHKM", "shift": "APAC"},
    "20305094397977": {"name": "Abhishek Srivastava", "slack" : "U05F3EVQXEH", "shift": "EMEA"},
    "18216981797273": {"name": "Shiekh Furqaan Ahmad", "slack" : "U0562STKX9A", "shift": "PST"},
    "14618544026137": {"name": "Yukthi K Mathad","slack" : "U04K22FNK1A", "shift": "EMEA"},
    "6952913318681": {"name": "Mohammed Jazeer B", "slack" : "U03GHSDLA4X", "shift": "EMEA"},
    "5268436329625": {"name": "Eric Manning", "slack" : "U038PQ0LWTG", "shift": "PST"},
    "903254421006": {"name": "Srinonti Biswas", "slack" : "U02HA8PG27M", "shift": "PST"},
    "420031063951": {"name": "Ankur Shrivastava", "slack" : "U02J3DWBY07", "shift": "PST"},
    "416520165912": {"name": "Ezhava Manuja", "slack" : "U022M2NT3MG", "shift": "APAC"},
    "395885198352": {"name": "Steven Decker", "slack": "U01A5UKPF38", "shift": "PST"}
}

ESCALATION_TAGS = {"escalated_customer", "escalated_yes"}

def get_day_of_week(target_date=None):
    """
    Returns the day of the week as a string.
    If no date is passed, it uses the current UTC date.
    """
    if target_date is None:
        target_date = datetime.utcnow()
    return target_date.strftime("%A")

def determine_shift():
    ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    hour = ist_now.hour
    if 6 <= hour < 15:
        return "APAC"
    elif 14 <= hour < 23:
        return "EMEA"
    else:
        return "PST"

def get_shift_start_time(shift_name):
    ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    ist_today = ist_now.date()
    shift_times = {
        "APAC": dt_time(6, 0),
        "EMEA": dt_time(14, 0),
        "PST": dt_time(21, 0)
    }
    shift_ist = datetime.combine(ist_today, shift_times[shift_name])
    if shift_name == "PST" and ist_now.time() < dt_time(6, 0):
        shift_ist -= timedelta(days=1)
    return shift_ist - timedelta(hours=5, minutes=30)

def fetch_tickets():
    try:
        tickets = []
        url = f"https://{ZENDESK_DOMAIN}/api/v2/search.json?query=type:ticket status<solved"
        auth = (f"{ZENDESK_EMAIL}/token", ZENDESK_TOKEN)
        while url:
            r = requests.get(url, auth=auth, headers=headers)
            r.raise_for_status()
            data = r.json()
            tickets.extend(data.get("results", []))
            url = data.get("next_page")
        return tickets
    except Exception as e:
        print(f"Fetch error: {e}")
        return []

def fetch_escalated_tickets_by_audit(tickets, shift_start):
    ids = []
    for t in tickets:
        aid = str(t.get("assignee_id"))
        if aid not in AGENT_MAP:
            continue
        try:
            url = f"https://{ZENDESK_DOMAIN}/api/v2/tickets/{t['id']}/audits.json"
            auth = (f"{ZENDESK_EMAIL}/token", ZENDESK_TOKEN)
            r = requests.get(url, auth=auth, headers=headers)
            r.raise_for_status()
            audits = r.json().get("audits", [])
        except:
            continue
        for a in audits:
            if datetime.fromisoformat(a["created_at"].rstrip("Z")) <= shift_start:
                continue
            for e in a["events"]:
                if e.get("field") == "tags" and ESCALATION_TAGS & set(e.get("value", [])):
                    ids.append(str(t["id"]))
                    break
            else:
                continue
            break
    return ids

def fetch_assigned_tickets_by_audit(tickets, shift_start_utc):
    assignment_map = {aid: [] for aid in AGENT_MAP}
    auth = (f"{ZENDESK_EMAIL}/token", ZENDESK_TOKEN)

    for ticket in tickets:
        ticket_id = ticket.get("id")
        try:
            url = f"https://{ZENDESK_DOMAIN}/api/v2/tickets/{ticket_id}/audits.json"
            response = requests.get(url, auth=auth, headers=headers)
            response.raise_for_status()
            audits = response.json().get("audits", [])
        except Exception as e:
            print(f"Failed to fetch audit for ticket {ticket_id}: {e}")
            continue

        for audit in audits:
            audit_time = datetime.fromisoformat(audit["created_at"].rstrip("Z"))
            if audit_time <= shift_start_utc:
                continue

            events = audit.get("events", [])
            assignee_event = next((e for e in events if e.get("field_name") == "assignee_id"), None)
            status_event = next((e for e in events if e.get("field_name") == "status"), None)

            if assignee_event and status_event:
                if (
                    status_event.get("value") == "open" and
                    status_event.get("previous_value") == "new" and
                    str(assignee_event.get("value")) in AGENT_MAP
                ):
                    aid = str(assignee_event.get("value"))
                    assignment_map[aid].append(str(ticket_id))
                    break  # Only count once per ticket

    return assignment_map

def fetch_updated_tickets_by_audit(tickets, shift_start_utc):
    from collections import defaultdict
    import requests

    status_transitions = {
        ("open", "pending"),
        ("open", "hold"),
        ("open", "solved"),
        ("pending", "hold"),
        ("pending", "solved"),
        ("hold", "solved")
    }

    relaxed_transitions = {
        ("open", "open"),
        ("pending", "pending"),
        ("hold", "hold")
    }

    updated_map = {aid: [] for aid in AGENT_MAP}
    auth = (f"{ZENDESK_EMAIL}/token", ZENDESK_TOKEN)

    print("\n[INFO] Begin audit-based updated ticket analysis...\n")

    for ticket in tickets:
        aid = str(ticket.get("assignee_id"))
        ticket_id = ticket.get("id")

        if aid not in updated_map or not ticket_id:
            print(f"[SKIP] Ticket {ticket_id} has no valid assignee.")
            continue

        try:
            url = f"https://{ZENDESK_DOMAIN}/api/v2/tickets/{ticket_id}/audits.json"
            response = requests.get(url, auth=auth,headers=headers)
            response.raise_for_status()
            audits = response.json().get("audits", [])
        except Exception as e:
            print(f"[ERROR] Failed to fetch audits for ticket {ticket_id}: {e}")
            continue

        ticket_already_counted = False

        for audit in audits:
            created_at = audit.get("created_at")
            if not created_at:
                continue

            audit_time = datetime.fromisoformat(created_at.rstrip("Z"))
            if audit_time <= shift_start_utc:
                continue

            events = audit.get("events", [])
            has_any_comment = any(e.get("type") == "Comment" for e in events)
            matched_status_change = None

            for e in events:
                if e.get("type") == "Change" and e.get("field_name") == "status":
                    prev = e.get("previous_value")
                    new = e.get("value")
                    if (prev, new) in status_transitions or (prev, new) in relaxed_transitions:
                        matched_status_change = (prev, new)
                        break

            if has_any_comment and (matched_status_change or matched_status_change is None):
                if ticket_id not in updated_map[aid]:
                    updated_map[aid].append(str(ticket_id))
                    print(f"[MATCH] ✅ Ticket {ticket_id} | Agent: {aid} | Time: {audit_time} | Status: {matched_status_change or 'N/A (relaxed)'}")
                    ticket_already_counted = True
                    break  # One match per ticket

            elif not has_any_comment:
                print(f"[SKIP] 🕵️ No comment on Ticket {ticket_id} during audit at {audit_time}. Status change = {matched_status_change}")
            else:
                print(f"[NO STATUS] Comment found, but no status field event. Ticket: {ticket_id}")

    print("\n[INFO] Finished audit scan for ticket updates.\n")
    return updated_map

def fetch_dsat_tickets_by_audit(tickets, shift_start):
    ids = []
    DSAT_ESCALATION_TAGS = {"dsat"}
    auth = (f"{ZENDESK_EMAIL}/token", ZENDESK_TOKEN)
    for t in tickets:
        aid = str(t.get("assignee_id"))
        if aid not in AGENT_MAP:
            continue
        try:
            url = f"https://{ZENDESK_DOMAIN}/api/v2/tickets/{t['id']}/audits.json"
            r = requests.get(url, auth=auth, headers=headers)
            r.raise_for_status()
            audits = r.json().get("audits", [])
        except:
            continue
        for a in audits:
            if datetime.fromisoformat(a["created_at"].rstrip("Z")) <= shift_start:
                continue
            for e in a["events"]:
                if e.get("field_name") == "tags" and DSAT_ESCALATION_TAGS & set(e.get("value", [])):
                    ids.append(str(t["id"]))
                    break
            else:
                continue
            break
    return ids

def fetch_tier_1_2_tickets_by_audit(tickets, shift_start):
    ids = []
    TIER_1_2_TAGS = {"tier_1", "tier_2"}
    auth = (f"{ZENDESK_EMAIL}/token", ZENDESK_TOKEN)
    for t in tickets:
        aid = str(t.get("assignee_id"))
        if aid not in AGENT_MAP:
            continue

        ticket_id = t["id"]

        try:
            url = f"https://{ZENDESK_DOMAIN}/api/v2/tickets/{ticket_id}/audits.json"
            r = requests.get(url, auth=auth, headers=headers)
            r.raise_for_status()
            audits = r.json().get("audits", [])
        except Exception as e:
            print(f"[Error] Failed fetching audits for ticket {ticket_id}: {e}")
            continue

        for a in audits:
            audit_time = datetime.fromisoformat(a["created_at"].rstrip("Z"))
            if audit_time < shift_start:
                continue

            for e in a["events"]:
                if e.get("field_name") == "tags":
                    tag_set = set(tag.lower() for tag in e.get("value", []))
                    if TIER_1_2_TAGS & tag_set:
                        ids.append(str(ticket_id))
                        print(f"[MATCH] ✅ Ticket {ticket_id} matched tier_1/2 at {audit_time}")
                        break
            else:
                continue
            break

    return ids

def summarize_tickets(tickets, escalated_ids, assigned_map,updated_map):
    current_shift = determine_shift()
    shift_start = get_shift_start_time(current_shift)
    summary = {aid: {
        "Total Tickets": 0,
        "Escalated Tickets": 0,
        "Escalated Ticket IDs": [],
        "Open Tickets": 0,
        "Tickets Updated in the Shift": len(updated_map.get(aid, [])),
        "Tickets Assigned in the Shift": len(assigned_map.get(aid, []))
    } for aid in AGENT_MAP}

    for t in tickets:
        aid = str(t.get("assignee_id"))
        existing_tags = t.get("tags", [])
        tier_1_2_tags = ["tier_1", "tier_2"]
        if aid not in summary:
            continue
        summary[aid]["Total Tickets"] += 1
        if str(t["id"]) in escalated_ids:
            summary[aid]["Escalated Tickets"] += 1
            summary[aid]["Escalated Ticket IDs"].append(str(t["id"]))
        if t.get("status") == "open":
            summary[aid]["Open Tickets"] += 1
    return summary

def format_message(summary):
    shift = determine_shift()
    lines = [f"📊 *Zendesk Summary Report for {shift}:*\n\n"]
    for aid, s in summary.items():
        agent = AGENT_MAP.get(aid)
        if not agent or agent["shift"] != shift:
            continue
        lines.append(f"<@{agent['slack']}>:")
        lines.append(f"Total Tickets: {s['Total Tickets'] or 'None'}")
        lines.append(f"Escalated Tickets: {s['Escalated Tickets'] or 'None'}")
        lines.append(f"Escalated Ticket IDs: {s['Escalated Ticket IDs'] or 'None'}")
        lines.append(f"Open Tickets: {s['Open Tickets'] or 'None'}")
        lines.append(f"Tickets Updated in the Shift: {s['Tickets Updated in the Shift'] or 'None'}")
        lines.append(f"Tickets Assigned in the Shift: {s['Tickets Assigned in the Shift'] or 'None'}\n")
    result = "\n".join(lines)
    print(result)
    return result

def post_to_slack(slack_webhook_url, message_text):
    payload = {
        "text": message_text
    }
    try:
        response = requests.post(slack_webhook_url, json=payload)
        response.raise_for_status()
        print("[✅] Slack message posted successfully.")
    except requests.exceptions.RequestException as e:
        print(f"[❌] Failed to post to Slack: {e}")

def post_to_zapier_webhook(webhook_url, payload):
    try:
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
        print("[✅] Successfully sent data to Zapier.")
    except requests.exceptions.RequestException as e:
        print(f"[❌] Failed to send to Zapier: {e}")



def main():
    print("Fetching tickets...")
    tickets = fetch_tickets()
    print(f"Fetched {len(tickets)}")
    tier_1_2_open = 0
    tier_1_2_tags = {"tier_1", "tier_2"}

    current_shift = determine_shift()
    shift_start = get_shift_start_time(current_shift)

    print("Auditing escalations...")
    escalated = fetch_escalated_tickets_by_audit(tickets, shift_start)
    print(f"Escalated IDs: {escalated}")

    print("Auditing assigned...")
    assigned_map = fetch_assigned_tickets_by_audit(tickets, shift_start)
    total_assigned_count = sum(len(v) for v in assigned_map.values())

    print("Auditing updates...")
    updated_map = fetch_updated_tickets_by_audit(tickets, shift_start)

    print("Summarizing...")
    summary = summarize_tickets(tickets, escalated, assigned_map, updated_map)

    print("Formatting...")
    format_message(summary)

    print("Posting message to Slack channel")
    final_message = format_message(summary)

    dsats = fetch_dsat_tickets_by_audit(tickets,shift_start)
    #tier_1_2_open = fetch_tier_1_2_tickets_by_audit(tickets,shift_start)

    if current_shift == "APAC":
        try:
            post_to_slack(SLACK_WEBHOOK_URL_APAC, final_message)
        except Exception as e:
            print(f"Error posting message to slack {e}")
    elif current_shift == "EMEA":
        try:
            post_to_slack(SLACK_WEBHOOK_URL_EMEA, final_message)
        except Exception as e:
            print(f"Error posting message to slack {e}")
    else:
        try:
            post_to_slack(SLACK_WEBHOOK_URL_US, final_message)
        except Exception as e:
            print(f"Error posting message to slack {e}")

    day_of_week = get_day_of_week()  # e.g. "Monday"

    # Total counts across all engineers for this shift
    total_updated = sum(len(v) for v in updated_map.values())
    total_open = sum(1 for t in tickets if t.get("status") == "open")
    total_escalated = len(escalated)
    total_dsat  = len(dsats)
    total_tier_1_2_open = tier_1_2_open


    zapier_payload = {
        "Day": day_of_week,
        "shift" : current_shift,
        "Assigned tickets": total_assigned_count,
        "Updated tickets": total_updated,
        "Open tickets": total_open,
        "Escalated tickets": total_escalated,
        "Tier 1/2 open tickets" : total_tier_1_2_open,
        "DSAT tickets" : total_dsat
        }

    if ZAPIER_WEBHOOK_URL:
        try:
            post_to_zapier_webhook(ZAPIER_WEBHOOK_URL,zapier_payload)
        except Exception as e:
            print(f"Error posting payload to zapier {e}")
    else:
        print("Zapier webhook not set. Try again")

def run_engineer_stats():
    main()
