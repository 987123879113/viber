import glob
import json
import os

chart_count = 0
event_start_idx = 0
with open("viberchart_list.h", "w") as outfile:
    all_events = []
    all_events_timestamps = []
    all_events_notes = []

    outfile.write("const ViberChart charts[VIBERCHART_CHARTCOUNT] PROGMEM = {\n")
    paths = list(glob.glob(os.path.join("charts", "*.json")))
    for path_idx, path in enumerate(paths):
        chart = json.load(open(path, "r"))

        for event in chart['events']:
            all_events.append(f"{{{event['timestamp']},{event['note_bits']}}}")
            all_events_timestamps.append(str(event['timestamp']))
            all_events_notes.append(str(event['note_bits']))

            if event['timestamp'] == 0:
                all_events[-1] = f"/* {len(all_events) - 1} {chart['title']} */ " + all_events[-1]

        outfile.write(f"{{\"{chart['title']}\",{len(chart['events'])},{event_start_idx}}},")
        event_start_idx += len(chart['events'])
        chart_count += 1

    outfile.write("};\n")

    outfile.write("const uint32_t event_timestamps[%d] PROGMEM = {\n" % (len(all_events_timestamps)))
    outfile.write(",\n".join(all_events_timestamps))
    outfile.write("};\n")

    outfile.write("const uint8_t event_notes[%d] PROGMEM = {\n" % (len(all_events_notes)))
    outfile.write(",\n".join(all_events_notes))
    outfile.write("};\n")


with open("viberchart_meta.h", "w") as outfile:
    outfile.write("#define VIBERCHART_CHARTCOUNT %d\n" % (chart_count))