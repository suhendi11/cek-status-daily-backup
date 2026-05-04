#!/usr/bin/env python3
import subprocess
import json
from datetime import datetime, timedelta, timezone

RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
CYAN = '\033[0;36m'
BLUE = '\033[0;34m'
RESET = '\033[0m'
NC = RESET

def color_status(status):

    if status == "OK":
        return f"{GREEN}OK{RESET}"

    elif status == "FAIL":
        return f"{RED}FAIL{RESET}"

    else:
        return f"{YELLOW}{status}{RESET}"


# OCI PROFILE

PROFILE_ILCS = "DEFAULT"
PROFILE_PELINDO = "PELINDO-SIN"


# COMPARTMENT

VOLUME_COMPARTMENT_ID_ILCS = "ocid1.compartment.oc1"


# VOLUME LIST

VOLUMES_ILCS = [
    ("TPK-009-WAS01 (Boot Volume)", "boot",
     "ocid1.bootvolume.oc1"),
]


# DATABASE LIST

DATABASES_ILCS = [
    ("DBTOSBLW",
     "ocid1.database.oc1"),
     
]

# PELINDO
PROFILE_PELINDO = "PELINDO-SIN"

DATABASES_PELINDO = [
    ("madra",
     "ocid1.database.oc1""),
    
]



# STATUS TABLE DASHBOARD

status_table = []


# COMMAND RUNNER

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(RED + f"Error executing: {cmd}" + NC)
        print(result.stderr)
        return None
    return result.stdout


# DATE CALCULATION

now_wib = datetime.now(timezone(timedelta(hours=7)))
target_date = now_wib.date() - timedelta(days=1)

# WINDOW BACKUP
window_start = datetime.combine(
    target_date, datetime.min.time()
).replace(tzinfo=timezone(timedelta(hours=7)))

window_end = window_start + timedelta(days=1, hours=6)

print(YELLOW + "\nMONITORING STATUS DAILY BACKUP\n" + RESET)
print(f"Daily Backup period {target_date} (WIB)\n")


# COUNTER

total_success = 0
total_failed = 0
total_inprogress = 0
failed_list = []


# CHECK VOLUMES

def check_volumes(profile, compartment_id, volumes):

    global total_success, total_failed, total_inprogress, failed_list

    if not volumes:
        return

    print(CYAN + "BOOT & BLOCK VOLUME CHECK\n" + RESET)

    for name, vol_type, ocid in volumes:

        print(CYAN + f"Checking: {name}" + RESET)

        if vol_type == "boot":
            cmd = f"oci bv boot-volume-backup list --profile {profile} --boot-volume-id {ocid} --compartment-id {compartment_id} --all"
        else:
            cmd = f"oci bv backup list --profile {profile} --volume-id {ocid} --compartment-id {compartment_id} --all"

        output = run_cmd(cmd)

        found = False

        if output:

            data = json.loads(output)

            backups = sorted(
                data.get("data", []),
                key=lambda x: x.get("time-created", ""),
                reverse=True
            )

            for backup in backups:

                time_created = backup.get("time-created")
                time_request = backup.get("time-request-received")
                status = backup.get("lifecycle-state", "UNKNOWN")

                if not time_created:
                    continue

                finish_wib = datetime.fromisoformat(
                    time_created.replace("Z", "+00:00")
                ).astimezone(timezone(timedelta(hours=7)))

                if window_start <= finish_wib <= window_end:

                    found = True

                    start_short = "--"

                    if time_request:

                        start_wib = datetime.fromisoformat(
                            time_request.replace("Z", "+00:00")
                        ).astimezone(timezone(timedelta(hours=7)))

                        print(f"  Start (WIB)   : {start_wib}")
                        start_short = start_wib.strftime("%H:%M")

                    print(f"  Finish (WIB)  : {finish_wib}")
                    finish_short = finish_wib.strftime("%H:%M")

                    if status == "AVAILABLE":
                        print("  Status        : " + GREEN + status + RESET)
                        total_success += 1
                        short_status = "OK"

                    elif status == "FAILED":
                        print("  Status        : " + RED + status + RESET)
                        total_failed += 1
                        failed_list.append(name)
                        short_status = "FAIL"

                    else:
                        print("  Status        : " + BLUE + status + RESET)
                        total_inprogress += 1
                        short_status = "RUN"

                    status_table.append((name, short_status, start_short, finish_short))

                    break

        if not found:

            print(RED + f"  ❌ Backup period {target_date} TIDAK ditemukan!" + RESET)
            total_failed += 1
            failed_list.append(name)

            status_table.append((name, "FAIL", "--", "--"))

        print("-" * 60)


# CHECK DATABASE

def check_databases(profile, databases):

    global total_success, total_failed, total_inprogress, failed_list

    print("\n" + CYAN + "DATABASE BACKUP CHECK\n" + RESET)

    for db_name, db_ocid in databases:

        region = "ap-singapore-1"

        if db_name.lower() == "pptospk":
            region = "ap-batam-1"

        print(CYAN + f"Checking: {db_name}" + RESET)

        cmd = f"oci db backup list --profile {profile} --database-id {db_ocid} --region {region} --all"

        output = run_cmd(cmd)

        found = False

        if not output:
            print(RED + "  ❌ Tidak bisa mengambil data backup!" + RESET)
            total_failed += 1
            failed_list.append(db_name)
            status_table.append((db_name, "FAIL", "--", "--"))
            continue

        try:
            data = json.loads(output)
        except:
            print(RED + "  ❌ JSON parse error!" + RESET)
            total_failed += 1
            failed_list.append(db_name)
            status_table.append((db_name, "FAIL", "--", "--"))
            continue

        valid_backups = [
            b for b in data.get("data", [])
            if b.get("time-ended") is not None
        ]

        if not valid_backups:
            print(RED + "  ❌ Tidak ada backup valid!" + NC)
            total_failed += 1
            failed_list.append(db_name)
            status_table.append((db_name, "FAIL", "--", "--"))
            continue

        backups = sorted(
            valid_backups,
            key=lambda x: x["time-ended"],
            reverse=True
        )

        for backup in backups:

            time_started = backup.get("time-started")
            time_ended = backup.get("time-ended")
            status = backup.get("lifecycle-state", "UNKNOWN")

            finish_wib = datetime.fromisoformat(
                time_ended.replace("Z", "+00:00")
            ).astimezone(timezone(timedelta(hours=7)))

            if window_start <= finish_wib <= window_end:

                found = True

                start_short = "--"

                if time_started:

                    start_wib = datetime.fromisoformat(
                        time_started.replace("Z", "+00:00")
                    ).astimezone(timezone(timedelta(hours=7)))

                    print(f"  Start (WIB)   : {start_wib}")
                    start_short = start_wib.strftime("%H:%M")

                print(f"  Finish (WIB)  : {finish_wib}")
                finish_short = finish_wib.strftime("%H:%M")

                if status in ["ACTIVE", "COMPLETED"]:
                    print("  Status        : " + GREEN + status + NC)
                    total_success += 1
                    short_status = "OK"

                elif status == "FAILED":
                    print("  Status        : " + RED + status + NC)
                    total_failed += 1
                    failed_list.append(db_name)
                    short_status = "FAIL"

                else:
                    print("  Status        : " + BLUE + status + NC)
                    total_inprogress += 1
                    short_status = "RUN"

                status_table.append((db_name, short_status, start_short, finish_short))

                break

        if not found:

            print(RED + f"  ❌ Backup period {target_date} TIDAK ditemukan!" + NC)
            total_failed += 1
            failed_list.append(db_name)
            status_table.append((db_name, "FAIL", "--", "--"))

        print("-" * 60)


# DASHBOARD 


def print_status_dashboard():

    print("\nBACKUP STATUS DASHBOARD\n")

    half = (len(status_table) + 1) // 2
    left = status_table[:half]
    right = status_table[half:]

    line = "-" * 120

    print(line)
    print(f"{'No':<3} {'Resource':<33} {'Status':<6} {'Start':<6} {'End':<6}  | "
          f"{'No':<3} {'Resource':<33} {'Status':<6} {'Start':<6} {'End':<6}")
    print(line)

    for i in range(half):

        # LEFT
        l_no = i + 1
        l_name, l_st, l_s, l_e = left[i]

        # status tetap 2 char supaya alignment stabil
        l_status_plain = f"{l_st:<2}"
        l_status = color_status(l_status_plain)

        left_text = (
            f"{l_no:<3} "
            f"{l_name:<35} "
            f"{l_status}   "
            f"{l_s:<6} "
            f"{l_e:<6}"
        )

        # RIGHT
        if i < len(right):

            r_no = i + half + 1
            r_name, r_st, r_s, r_e = right[i]

            r_status_plain = f"{r_st:<2}"
            r_status = color_status(r_status_plain)

            right_text = (
                f"{r_no:<3} "
                f"{r_name:<35} "
                f"{r_status}   "
                f"{r_s:<6} "
                f"{r_e:<6}"
            )

        else:
            right_text = ""

        print(f"{left_text}   | {right_text}")

    print(line)

# RUN CHECK

check_volumes(PROFILE_ILCS, VOLUME_COMPARTMENT_ID_ILCS, VOLUMES_ILCS)
check_databases(PROFILE_ILCS, DATABASES_ILCS)
check_databases(PROFILE_PELINDO, DATABASES_PELINDO)

# PRINT DASHBOARD
print_status_dashboard()


# SUMMARY


volume_total = len(VOLUMES_ILCS)
db_ilcs_total = len(DATABASES_ILCS)
db_pln_total = len(DATABASES_PELINDO)

total_resource = volume_total + db_ilcs_total + db_pln_total

success_rate = (total_success / total_resource) * 100 if total_resource else 0

# STATUS
if total_failed > 0:
    status_icon = "🔴"
    overall_status = "CRITICAL"
elif total_inprogress > 0:
    status_icon = "🟡"
    overall_status = "WARNING"
else:
    status_icon = "🟢"
    overall_status = "HEALTHY"

summary = "\n"
summary += "DAILY BACKUP REPORT SUMMARY\n\n"

summary += f"📅 Period  {target_date}\n\n"

summary += "RESOURCE ────────\n\n"
summary += f"💾 Volume           : {volume_total}\n"
summary += f"🗄 Database ILCS     : {db_ilcs_total}\n"
summary += f"🗄 Database Pelindo  : {db_pln_total}\n\n"

summary += f"📦 Total            : {total_resource}\n\n"

summary += "RESULT ──────────\n\n"
summary += f"✅ Success       : {total_success}\n"
summary += f"❌ Failed        : {total_failed}\n"
summary += f"⏳ Progress      : {total_inprogress}\n\n"

summary += "📈 Success Rate\n"
summary += f"{success_rate:.2f} %\n\n"

summary += "FAILED ──────────\n\n"

if failed_list:
    for item in failed_list:
        summary += f"❌ {item}\n"
else:
    summary += "Tidak ada resource gagal\n"

summary += "\nSTATUS ──────────\n\n"
summary += f"{status_icon} {overall_status}\n"

print(summary)
