import argparse
import copy
import json
import os


class CsqReader:
    def __init__(self, data):
        self.data = data
        self.bpm_list = None
        self.chunks = self.parse()


    def export_json(self, filename=None):
        chunks = []

        for chunk in self.chunks[::]:
            sanitized_events = []

            if chunk['type'] == "tempo":
                sanitized_events = {
                    'tick_rate': chunk['events']['tick_rate'],
                    'events': [],
                }

                for event in sorted(chunk['events']['events'], key=lambda x:x['start_offset']):
                    sanitized_events['events'].append({
                        'measure': event['start_measure'],
                        'timestamp': event['start_timestamp'],
                        '_bpm': event['bpm'],
                    })

                sanitized_events['events'].append({
                    'measure': event['end_measure'],
                    'timestamp': event['end_timestamp'],
                    '_bpm': event['bpm'],
                })

            elif chunk['type'] in ["events", "lamps"]:
                for event in chunk['events']:
                    sanitized_events.append({
                        '_meta_timestamp': event['timestamp'],
                        'measure': event['measure'],
                        'event': event['event'],
                    })

            elif chunk['type'] == "notes":
                sanitized_events = {
                    'chart_type': chunk['events']['chart_type'],
                    'events': [],
                }

                for event in chunk['events']['events']:
                    sanitized_events['events'].append({
                        '_meta_timestamp': event['timestamp'],
                        'measure': event['measure'],
                        'notes': event['notes'],
                    })

                    if 'extra' in event:
                        sanitized_events['events'][-1]['extra'] = event['extra']

            elif chunk['type'] == "anim":
                for event in chunk['events']:
                    sanitized_events.append({
                        '_meta_timestamp': event['timestamp'],
                        'measure': event['measure'],
                        'cmd_raw': event['cmd_raw'],
                        'param_raw': event['param_raw'],
                        'clip_filename': event['clip_filename'],
                    })

            chunk['events'] = sanitized_events

            chunks.append(chunk)

        if filename:
            import json
            json.dump(chunks, open(filename, "w"), indent=4, ensure_ascii=False)

        return chunks


    def calculate_measure(self, value):
        m = int(value / 4096)
        n = (value - (m * 4096)) / 4096
        return (m, n)


    def calculate_timestamp(self, value):
        if not self.bpm_list:
            return None

        for bpm_info in self.bpm_list:
            if value >= bpm_info['start_offset'] and value < bpm_info['end_offset']:
                break

        timestamp = bpm_info['start_timestamp'] + (((value - bpm_info['start_offset']) / 1024) / bpm_info['bpm']) * 60

        return timestamp * 1000


    def calculate_offset(self, value):
        if not self.bpm_list:
            return None

        for bpm_info in self.bpm_list:
            if value >= bpm_info['start_data'] and value < bpm_info['end_data']:
                break

        offset = bpm_info['start_offset'] + (bpm_info['end_offset'] - bpm_info['start_offset']) * ((value - bpm_info['start_data']) / (bpm_info['end_data'] - bpm_info['start_data']))

        return offset


    def get_bpm(self, value):
        if not self.bpm_list:
            return None

        for bpm_info in self.bpm_list:
            if value >= bpm_info['start_offset'] and value < bpm_info['end_offset']:
                break

        return bpm_info['bpm']


    def parse(self):
        data = self.data

        chunks = []

        chunk_parsers = {
            'tempo': self.parse_tempo_chunk,
            'events': self.parse_events_chunk,
            'notes': self.parse_note_events_chunk,
            'lamps': self.parse_lamp_events_chunk,
            # 'anim': self.parse_anim_chunk_raw,
        }

        while data:
            chunk_len = int.from_bytes(data[:4], 'little')

            if len(data) - 4 <= 0:
                break

            chunk_type = int.from_bytes(data[4:6], 'little')
            chunk_raw = data[6:chunk_len]
            data = data[chunk_len:]

            chunks.append({
                'type': {
                    0x01: 'tempo',
                    0x02: 'events',
                    0x03: 'notes',
                    0x04: 'lamps',
                    0x05: 'anim',
                }[chunk_type],
                '_raw': chunk_raw,
            })

        bpm_chunk = None
        for chunk in chunks:
            if chunk['type'] == "tempo":
                chunk['events'] = chunk_parsers.get(chunk['type'], lambda x: [])(chunk['_raw'])
                bpm_chunk = copy.deepcopy(chunk)
                break

        if bpm_chunk is None:
            print("Couldn't find BPM chunk")
            exit(1)

        self.bpm_list = bpm_chunk['events']['events']

        for chunk in chunks:
            chunk['events'] = chunk_parsers.get(chunk['type'], lambda x: [])(chunk['_raw'])

            # if 'anim' in chunk['type']:
            #     render_animation(chunk['events'], "output_anim", mp3_filename, bpm_chunk['events'])

            del chunk['_raw']

        return chunks


    def parse_tempo_chunk(self, data):
        tick_rate = int.from_bytes(data[:2], 'little')
        count = int.from_bytes(data[2:4], 'little')
        assert(int.from_bytes(data[4:6], 'little') == 0)

        time_offsets = [int.from_bytes(data[6+x*4:6+(x+1)*4], 'little', signed=True) for x in range(count)]
        time_data = [int.from_bytes(data[6+x*4:6+(x+1)*4], 'little', signed=True) for x in range(count, count * 2)]

        sample_rate = 294 * tick_rate

        bpm_changes = []
        for i in range(1, count):
            start_timestamp = time_data[i-1] / tick_rate
            end_timestamp = time_data[i] / tick_rate
            time_delta = (end_timestamp - start_timestamp) * 1000
            offset_delta = (time_offsets[i] - time_offsets[i-1])
            bpm = 60000 / (time_delta / (offset_delta / 1024)) if offset_delta != 0 else 0

            bpm_changes.append({
                'start_offset': time_offsets[i-1],
                'start_measure': self.calculate_measure(time_offsets[i-1]),
                'end_offset': time_offsets[i],
                'end_measure': self.calculate_measure(time_offsets[i]),
                'start_data': time_data[i-1],
                'end_data': time_data[i],
                'start_timestamp': start_timestamp,
                'end_timestamp': end_timestamp,
                'bpm': bpm
            })

        return {
            'tick_rate': tick_rate,
            'events': bpm_changes,
        }


    def parse_events_chunk(self, data):
        assert(int.from_bytes(data[:2], 'little') == 1)
        count = int.from_bytes(data[2:4], 'little')
        assert(int.from_bytes(data[4:6], 'little') == 0)

        event_offsets = [int.from_bytes(data[6+x*4:6+(x+1)*4], 'little', signed=True) for x in range(count)]
        event_data = [int.from_bytes(data[6+(count*4)+x*2:6+(count*4)+(x+1)*2], 'little') for x in range(count)]

        event_lookup = {
            0x0202: "start", # Display "Ready?"
            0x0302: "end", # End of chart
            0x0402: "clear", # End of stage/move to result screen
        }

        events = []
        for i in range(count):
            events.append({
                'offset': event_offsets[i],
                'measure': self.calculate_measure(event_offsets[i]),
                'timestamp': self.calculate_timestamp(event_offsets[i]),
                '_bpm': self.get_bpm(event_offsets[i]),
                'event': event_lookup.get(event_data[i], event_data[i])
            })

        return events


    def parse_note_events_chunk(self, data):
        def clamp(val, boundary):
            if (val % boundary) == 0:
                return val

            return val + (boundary - (val % boundary))

        chart_type = int.from_bytes(data[:2], 'little')
        count = int.from_bytes(data[2:4], 'little')
        assert(int.from_bytes(data[4:6], 'little') == 0)

        chart_type = {
            0x0114: "single-basic",
            0x0214: "single-standard",
            0x0314: "single-heavy",
            0x0414: "single-beginner",
            0x0614: "single-challenge",

            0x0116: "solo-basic",
            0x0216: "solo-standard",
            0x0316: "solo-heavy",
            0x0416: "solo-beginner",
            0x0616: "solo-challenge",

            0x0118: "double-basic",
            0x0218: "double-standard",
            0x0318: "double-heavy",
            0x0418: "double-beginner",
            0x0618: "double-challenge",

            0x1024: "double-battle",

            # fxxx range is just a hack and not an official chart range
            0xf116: "solo3-basic",
            0xf216: "solo3-standard",
            0xf316: "solo3-heavy",
            0xf416: "solo3-beginner",
            0xf616: "solo3-challenge",
        }.get(chart_type, chart_type)

        event_offsets = [int.from_bytes(data[6+x*4:6+(x+1)*4], 'little', signed=True) for x in range(count)]
        event_data = data[6+(count*4):clamp(6+(count*4)+count, 2)]
        event_extra_data = data[clamp(6+(count*4)+count, 2):]

        events = []
        for offset in event_offsets:
            event = {
                'offset': offset,
                'measure': self.calculate_measure(offset),
                'timestamp': self.calculate_timestamp(offset),
                '_bpm': self.get_bpm(offset),
            }

            note_raw = event_data[0]
            event_data = event_data[1:]

            if note_raw == 0:
                note_raw = event_extra_data[0]
                extra_type = event_extra_data[1]
                event_extra_data = event_extra_data[2:]

                if (extra_type & 1) != 0:
                    event['extra'] = ['freeze_end']

                if (extra_type & ~1) != 0:
                    print("Unknown extra event: %02x" % extra_type)
                    exit(1)

            notes = []
            if note_raw == 0xff:
                notes.append('shock')

            else:
                for i in range(8):
                    if (note_raw & (1 << i)) != 0:
                        if "solo" in chart_type:
                            n = {
                                0x00: 'solo_l',
                                0x01: 'solo_d',
                                0x02: 'solo_u',
                                0x03: 'solo_r',
                                0x04: 'solo_ul',
                                0x06: 'solo_ur',
                            }[i]

                        else:
                            n = {
                                0x00: 'p1_l',
                                0x01: 'p1_d',
                                0x02: 'p1_u',
                                0x03: 'p1_r',
                                0x04: 'p2_l',
                                0x05: 'p2_d',
                                0x06: 'p2_u',
                                0x07: 'p2_r',
                            }[i]

                        notes.append(n)

            event['notes'] = notes

            events.append(event)

        # Add freeze start commands
        events = sorted(events, key=lambda x:x['offset'])
        for i in range(len(events)):
            if "freeze_end" in events[i].get('extra', []):
                for x in range(i-1, -1, -1):
                    if events[i]['notes'] == events[x]['notes']:
                        events[x]['extra'] = events[x].get('extra', []) + ['freeze_start']
                        break

        return {
            'chart_type': chart_type,
            'events': events,
        }


    def parse_lamp_events_chunk(self, data):
        assert(int.from_bytes(data[:2], 'little') == 1)
        count = int.from_bytes(data[2:4], 'little')
        assert(int.from_bytes(data[4:6], 'little') == 0)

        event_offsets = [int.from_bytes(data[6+x*4:6+(x+1)*4], 'little', signed=True) for x in range(count)]
        event_data = [data[6+(count*4)+x] for x in range(count)]

        events = []
        for i in range(count):
            events.append({
                'offset': event_offsets[i],
                'measure': self.calculate_measure(event_offsets[i]),
                'timestamp': self.calculate_timestamp(event_offsets[i]),
                '_bpm': self.get_bpm(event_offsets[i]),
                'event': event_data[i],
            })

        return events


    def parse_anim_chunk_raw(self, data):
        assert(int.from_bytes(data[:2], 'little') == 0) # What is this used for?
        count = int.from_bytes(data[2:4], 'little')
        assert(int.from_bytes(data[4:6], 'little') == 0)

        event_offsets = [int.from_bytes(data[6+x*4:6+(x+1)*4], 'little', signed=True) for x in range(count)]
        event_data = [data[6+(count*4)+x*4:6+(count*4)+(x+1)*4] for x in range(count)]

        filename_chunk_count = int.from_bytes(data[6+(count*8):6+(count*8)+4], 'little')
        filename_chunks = [int.from_bytes(data[6+(count*8)+4+x*4:6+(count*8)+4+(x+1)*4], 'little') for x in range(filename_chunk_count)]

        clip_filenames = []

        for chunk in filename_chunks:
            output_string = ""

            for i in range(6):
                c = chunk & 0x1f

                if c < 0x1b:
                    output_string += chr(c + 0x61)

                chunk >>= 5

            clip_filenames.append(output_string)

        events = []
        last_direction = 1
        for i in range(count):
            cmd = event_data[i][0]
            cmd_upper = (cmd >> 4) & 0x0f

            clip_idx = event_data[i][1]
            param = int.from_bytes(event_data[i][2:4], 'little')

            common_lookup = {
                0x14: "end",
                0x15: "ccclma",
                0x16: "ccclca",
                0x17: "ccddra",
                0x18: "ccdrga",
                0x19: "ccheaa",
                0x1a: "ccitaa",
                0x1b: "ccltaa",
                0x1c: "ccrgca",
                0x1d: "ccsaca",
            }

            clip_filename = common_lookup[clip_idx] if clip_idx in common_lookup else clip_filenames[clip_idx]

            event = {
                'offset': event_offsets[i],
                'measure': self.calculate_measure(event_offsets[i]),
                'timestamp': self.calculate_timestamp(event_offsets[i]),
                '_bpm': self.get_bpm(event_offsets[i]),
                'cmd_raw': cmd,
                'param_raw': param,
                'clip_filename': clip_filename
            }

            events.append(event)

        return events


    def parse_anim_chunk(self, data):
        return []


class CmsReader:
    def __init__(self, data):
        self.data = self.convert(data)


    def export_json(self, filename=None):
        # This is code from another tool I had sitting around.
        # I took the lazy way out and just convert it to a SSQ and then using CsqReader
        # instead of writing another chart reader.
        return CsqReader(self.data).export_json(filename)


    def convert(self, chart):
        chunks = []
        while len(chart) > 0:
            chunk_size = int.from_bytes(chart[:4], 'little')

            if chunk_size == 0:
                chunks.append([])
                chart = chart[4:]

            else:
                chunks.append(chart[4:chunk_size])
                chart = chart[chunk_size:]

        is_solo_cms = False
        for idx, chunk in enumerate(chunks):
            if not chunk:
                continue

            if idx > 0:
                if int.from_bytes(chunk[0x08:0x0c], 'little') != 0xffffffff:
                    print("Didn't find expected header for chart")
                    exit(1)

                chart_type = chunk[0] # 0 = single, 1 = solo??, 2 = double
                is_solo = chart_type == 1 # ??

                if is_solo:
                    is_solo_cms = True
                    break

        new_chunks = []
        for idx, chunk in enumerate(chunks):
            if not chunk:
                continue

            if idx == 0:
                # Tempo change chunk
                count = len(chunk) // 8

                l = bytearray()
                r = bytearray()

                diff = 1
                timing = 0x4b * diff

                for x in range(0, count * 2, 2):
                    idx = x * 4
                    point1 = int.from_bytes(chunk[idx:idx+4], 'little') * diff

                    idx = (x + 1) * 4
                    point2 = int.from_bytes(chunk[idx:idx+4], 'little') * diff

                    l += int.to_bytes(point1, 4, 'little')
                    r += int.to_bytes(point2, 4, 'little')

                chunk = bytearray()
                chunk += int.to_bytes(1, 2, 'little') # Chunk ID
                chunk += int.to_bytes(timing, 2, 'little') # Timing
                chunk += int.to_bytes(count, 4, 'little') # Entry count
                chunk += l
                chunk += r

            else:
                if int.from_bytes(chunk[0x08:0x0c], 'little') != 0xffffffff:
                    print("Didn't find expected header for chart")
                    exit(1)

                chart_type = chunk[0] # 0 = single, 1 = solo??, 2 = double
                diff = chunk[1]

                events = [(int.from_bytes(chunk[0x0c+i:0x0c+i+4], 'little'), chunk[0x0c+i+4:0x0c+i+8]) for i in range(0, len(chunk) - 0x0c, 8)]
                event_chunks = []
                end_timestamp = None

                for event in events:
                    if int.from_bytes(event[1], 'little') == 0xffffffff:
                        end_timestamp = event[0]
                        break

                    note = 0

                    p1_down = (event[1][0] & 0x10) != 0
                    p1_left = (event[1][0] & 0x01) != 0
                    p1_right = (event[1][1] & 0x10) != 0
                    p1_up = (event[1][1] & 0x01) != 0

                    p2_down = (event[1][2] & 0x10) != 0
                    p2_left = (event[1][2] & 0x01) != 0
                    p2_right = (event[1][3] & 0x10) != 0
                    p2_up = (event[1][3] & 0x01) != 0

                    note = (p1_right << 3) | (p1_up << 2) | (p1_down << 1) | p1_left
                    note |= ((p2_right << 3) | (p2_up << 2) | (p2_down << 1) | p2_left) << 4

                    event_chunks.append((event[0], note))

                chunk = bytearray()
                chunk += int.to_bytes(3, 2, 'little')

                if is_solo_cms:
                    if chart_type == 0:
                        chart_idx = 0x16 # 6 panel

                    elif chart_type == 1:
                        chart_idx = 0x14 # 4 panel

                    elif chart_type == 2:
                        chart_idx = 0x16 # 3 panel
                        diff += 0xf0 # This is a hack for 3 panel modes to be handled as edit charts

                    chunk += int.to_bytes(chart_idx, 1, 'little')

                else:
                    chunk += int.to_bytes(0x14 + (chart_type * 2), 1, 'little')

                chunk += int.to_bytes(diff + 1, 1, 'little')
                chunk += int.to_bytes(len(event_chunks), 4, 'little')

                for event in event_chunks:
                    chunk += int.to_bytes(event[0], 4, 'little')

                for event in event_chunks:
                    chunk += int.to_bytes(event[1], 1, 'little')

                if len(chunk) % 4 != 0:
                    chunk += bytearray([0] * (4 - (len(chunk) % 4))) # Padding which this section seems to require

            new_chunks.append(chunk)

        # Generate chart event timing chunk
        chunk = bytearray()
        chunk += int.to_bytes(2, 2, 'little')
        chunk += int.to_bytes(1, 2, 'little')
        chunk += int.to_bytes(5, 4, 'little')

        for x in [0xfffff000, 0xfffff000, 0, end_timestamp - 4096, end_timestamp]:
            chunk += int.to_bytes(x, 4, 'little')

        for x in [0x0104, 0x0201, 0x0202, 0x0203, 0x0204]:
            chunk += int.to_bytes(x, 2, 'big')

        if len(chunk) % 4 != 0:
            chunk += bytearray([0] * (4 - (len(chunk) % 4))) # Padding which this section seems to require

        # Lamp data (filler)
        lamp_chunk = bytearray()
        lamp_chunk += int.to_bytes(4, 2, 'little')
        lamp_chunk += int.to_bytes(1, 2, 'little')
        lamp_chunk += int.to_bytes(1, 4, 'little')
        lamp_chunk += int.to_bytes(0, 4, 'little') # Timestamp
        lamp_chunk += int.to_bytes(0x80, 1, 'little') # Set lamps to "off"

        if len(lamp_chunk) % 4 != 0:
            lamp_chunk += bytearray([0] * (4 - (len(lamp_chunk) % 4))) # Padding which this section seems to require

        # Video data (filler)
        video_chunk = bytearray()
        video_chunk += int.to_bytes(5, 2, 'little')
        video_chunk += int.to_bytes(0, 2, 'little')
        video_chunk += int.to_bytes(2, 4, 'little')
        video_chunk += int.to_bytes(0, 4, 'little') # Start Timestamp
        video_chunk += int.to_bytes(end_timestamp, 4, 'little') # End Timestamp
        video_chunk += int.to_bytes(0x00061d45, 4, 'little') # Video command
        video_chunk += int.to_bytes(0x00061d45, 4, 'little') # Video command
        video_chunk += int.to_bytes(0x00000001, 4, 'little') # Video file reference count
        video_chunk += int.to_bytes(0x00b52649, 4, 'little') # Some kind of video file reference

        if len(video_chunk) % 4 != 0:
            video_chunk += bytearray([0] * (4 - (len(video_chunk) % 4))) # Padding which this section seems to require

        new_chunks = [new_chunks[0]] + [chunk] + new_chunks[1:] #+ [lamp_chunk, video_chunk]
        new_chunks.append([])

        output = bytearray()

        for chunk in new_chunks:
            output += int.to_bytes(len(chunk) + 4 if chunk else 0, 4, 'little')

            if chunk:
                output += chunk

        return output


def convert_json_to_vibes(data, target_chart, package_info):
    output_events = {}

    for x in data:
        if x['type'] != "notes":
            continue

        if x['events']['chart_type'] != target_chart:
            continue

        key_states = {
            'p1_l': 0,
            'p1_d': 0,
            'p1_u': 0,
            'p1_r': 0,
        }

        key_state_timestamps = {
            'p1_l': 0,
            'p1_d': 0,
            'p1_u': 0,
            'p1_r': 0,
        }

        last_k = 0
        for event in sorted(x['events']['events'], key=lambda x:x['_meta_timestamp']):
            print(event)
            k = round(event['_meta_timestamp'] * 1000)
            if k not in output_events:
                output_events[k] = []
            val = 0 if "freeze_end" in event.get('extra', []) else 1
            output_events[k] += [{'name': x, 'value': val} for x in event['notes']]

            if val == 1:
                for x in event['notes']:
                    if key_states[x] != 0:
                        k2 = key_state_timestamps[x] + (k - key_state_timestamps[x]) // 2
                        k2_2 = key_state_timestamps[x] + 75000
                        k2 = k2_2 if k2_2 < k2 else k2

                        if k2 not in output_events:
                            output_events[k2] = []

                        output_events[k2] += [{'name': x, 'value': 0}]
                        print(k2)

            for x in event['notes']:
                if "freeze_start" in event.get('extra', []):
                    key_states[x] = 2
                elif "freeze_end" in event.get('extra', []):
                    key_states[x] = 0
                elif key_states[x] == 0:
                    key_states[x] = 1

                key_state_timestamps[x] = k

            last_k = k

    title = package_info.get('title', "Untitled")
    diff = {
        "single-beginner": "BEG",
        "single-basic": "BSC",
        "single-standard": "STD",
        "single-heavy": "HVY",
        "single-challenge": "CHA",
    }[target_chart]

    title = title[:20 - 4]
    title += " " + diff

    event_count = 0
    keys = sorted(output_events.keys())
    output = {
        'title': title,
        'events': [],
    }
    for k in keys:
        bit_lookup = {
            'p1_l': 0,
            'p1_d': 1,
            'p1_u': 2,
            'p1_r': 3,
        }
        note_bits = sum([x['value'] << bit_lookup[x['name']] for x in output_events[k]])
        note_bits |= sum([1 << bit_lookup[x['name']] for x in output_events[k]]) << 4
        output['events'].append({
            'timestamp': k - keys[0],
            'note_bits': note_bits,
        })
        event_count += 1

    assert(len(output_events.keys()) == event_count)

    return output, event_count



if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument('-i', '--input', help='Input folder', default=None, required=True)
    parser.add_argument('-c', '--chart', help='Chart to export', default=None, required=True, choices=["single-beginner", "single-basic", "single-standard", "single-heavy", "single-challenge"])

    args = parser.parse_args()

    package_info = {
        'music_id': os.path.splitext(os.path.basename(args.input))[0],
        'title': os.path.splitext(os.path.basename(args.input))[0],
    }
    package_path = os.path.join(os.path.dirname(args.input), "package.json")
    if os.path.exists(package_path):
        package_info = json.load(open(package_path, "r"))

    input_format = os.path.splitext(args.input)[-1].lower().strip('.')

    if input_format in ["ssq", "csq"]:
        reader = CsqReader(bytearray(open(args.input, "rb").read()))
        data = reader.export_json()

    elif input_format in ["cms"]:
        reader = CmsReader(bytearray(open(args.input, "rb").read()))
        data = reader.export_json()

    elif input_format == "json":
        import json
        data = json.load(open(args.input))

    print("Dumping vibes")
    vibes, event_count = convert_json_to_vibes(data, args.chart, package_info)

    os.makedirs("charts", exist_ok=True)
    json.dump(vibes, open(os.path.join("charts", f"chart_{package_info['music_id']}_{args.chart}.json"), "w"), indent=4)
