import struct


class Font:
    def __init__(self, path):
        data = open(path, "rb").read()
        tables = {}
        for i in range(struct.unpack(">H", data[4:6])[0]):
            tag, _, offset, length = struct.unpack(">4sIII", data[12 + 16 * i : 28 + 16 * i])
            tables[tag.decode()] = data[offset : offset + length]
        self.units = struct.unpack(">H", tables["head"][18:20])[0]
        count = struct.unpack(">H", tables["hhea"][34:36])[0]
        hmtx = tables["hmtx"]
        self.advances = [struct.unpack(">H", hmtx[4 * i : 4 * i + 2])[0] for i in range(count)]
        self.cmap = self._cmap(tables["cmap"])

    @staticmethod
    def _cmap(cmap):
        subtables = {}
        for i in range(struct.unpack(">H", cmap[2:4])[0]):
            platform, encoding, offset = struct.unpack(">HHI", cmap[4 + 8 * i : 12 + 8 * i])
            subtables[(platform, encoding)] = offset
        out = {}
        if (3, 10) in subtables:
            t = cmap[subtables[(3, 10)] :]
            for g in range(struct.unpack(">I", t[12:16])[0]):
                start, end, glyph = struct.unpack(">III", t[16 + 12 * g : 28 + 12 * g])
                for c in range(start, end + 1):
                    out[c] = glyph + c - start
            return out
        t = cmap[subtables[(3, 1)] :]
        segs = struct.unpack(">H", t[6:8])[0] // 2
        ends = struct.unpack(f">{segs}H", t[14 : 14 + 2 * segs])
        base = 16 + 2 * segs
        starts = struct.unpack(f">{segs}H", t[base : base + 2 * segs])
        deltas = struct.unpack(f">{segs}h", t[base + 2 * segs : base + 4 * segs])
        range_at = base + 4 * segs
        ranges = struct.unpack(f">{segs}H", t[range_at : range_at + 2 * segs])
        for s in range(segs):
            for c in range(starts[s], ends[s] + 1):
                if ranges[s] == 0:
                    glyph = (c + deltas[s]) & 0xFFFF
                else:
                    at = range_at + 2 * s + ranges[s] + 2 * (c - starts[s])
                    glyph = struct.unpack(">H", t[at : at + 2])[0]
                    glyph = (glyph + deltas[s]) & 0xFFFF if glyph else 0
                out[c] = glyph
        return out

    def width(self, text, size):
        total = 0
        for ch in text:
            glyph = self.cmap.get(ord(ch), 0)
            total += self.advances[min(glyph, len(self.advances) - 1)]
        return total * size / self.units
