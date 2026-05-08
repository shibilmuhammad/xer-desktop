import sys
import os
import pandas as pd

sys.path.append(os.path.abspath("."))
from modules.extractor import CompleteXERExtractor
from modules.scheduler import CPMScheduler

xer_path = "/Users/shibilmuhammad/Documents/Career/Al Amrah_Infra Package 01_Baseline Program Rev 00.xer"
extractor = CompleteXERExtractor(xer_path)
data = extractor.extract_all()
dfs = {t: pd.DataFrame(data.tables[t]) for t in data.tables if data.tables[t]}

sched = CPMScheduler()
cal_map = sched._build_calendars(dfs)
proj_cal_id = dfs['PROJECT'].iloc[0]['clndr_id']
proj_cal = cal_map.get(proj_cal_id)

f = pd.to_datetime('2026-03-23')
lf = pd.to_datetime('2026-08-30')

print("workdays_between:", proj_cal.workdays_between(f, lf))
print("calendar_days:", (lf.date() - f.date()).days)

