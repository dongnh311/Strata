from collections import Counter

def top_ips(lines: list[str]) -> list[tuple[str, int]]:
    counts = Counter()
    for line in lines:
        parts = line.split()
        if parts:
            counts[parts[0]] += 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:3]
