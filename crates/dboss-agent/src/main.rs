//! Minimal dependency-free Rust probe: no process management, SQL or tuning.
use std::collections::BTreeMap;
use std::fs;
use std::process::ExitCode;

fn parse_meminfo(raw: &str) -> BTreeMap<String, u64> {
    let mut values = BTreeMap::new();
    for line in raw.lines() {
        if let Some((k, v)) = line.split_once(':') {
            let mut parts = v.split_whitespace();
            if let Some(Ok(number)) = parts.next().map(str::parse::<u64>) {
                let scale = if parts.next() == Some("kB") { 1024 } else { 1 };
                if let Some(bytes) = number.checked_mul(scale) {
                    values.insert(k.to_string(), bytes);
                }
            }
        }
    }
    values
}

fn parse_arcstats(raw: &str) -> BTreeMap<String, u64> {
    let mut values = BTreeMap::new();
    for line in raw.lines() {
        let parts: Vec<&str> = line.split_whitespace().collect();
        if parts.len() == 3 && parts[1].parse::<u64>().is_ok() {
            if let Ok(value) = parts[2].parse::<u64>() {
                values.insert(parts[0].to_string(), value);
            }
        }
    }
    values
}

fn value(stats: &BTreeMap<String, u64>, key: &str) -> u64 {
    stats.get(key).copied().unwrap_or(0)
}

fn usage() {
    println!("dboss-agent 0.1.0 --host (read-only Linux memory + ZFS ARC metrics)");
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.is_empty() || matches!(args[0].as_str(), "--help" | "-h") {
        usage();
        return ExitCode::SUCCESS;
    }
    if args.as_slice() != ["--host"] {
        eprintln!("Unknown argument (use --host or --help).");
        return ExitCode::from(2);
    }
    let memory = match fs::read_to_string("/proc/meminfo") {
        Ok(text) => parse_meminfo(&text),
        Err(_) => {
            eprintln!("Unable to read /proc/meminfo; Linux required.");
            return ExitCode::from(1);
        }
    };
    let arc_data = fs::read_to_string("/proc/spl/kstat/zfs/arcstats");
    let arc_available = arc_data.is_ok();
    let arc = arc_data.map(|raw| parse_arcstats(&raw)).unwrap_or_default();
    let hits = value(&arc, "hits");
    let misses = value(&arc, "misses");
    let ratio = if hits.saturating_add(misses) == 0 {
        "null".to_string()
    } else {
        format!("{:.6}", hits as f64 / (hits as f64 + misses as f64))
    };
    // Fixed keys and numeric values only: no interpolation of untrusted
    // filesystem contents into raw JSON strings.
    println!(
        "{{\"agent\":\"dboss-rust-0.1.0\",\"read_only\":true,\"memory_bytes\":{{\"MemTotal\":{},\"MemAvailable\":{},\"SwapTotal\":{},\"SwapFree\":{}}},\"arc\":{{\"available\":{},\"size\":{},\"compressed_size\":{},\"uncompressed_size\":{},\"hits\":{},\"misses\":{},\"hit_ratio\":{}}}}}",
        value(&memory, "MemTotal"), value(&memory, "MemAvailable"),
        value(&memory, "SwapTotal"), value(&memory, "SwapFree"),
        arc_available, value(&arc, "size"), value(&arc, "compressed_size"),
        value(&arc, "uncompressed_size"), hits, misses, ratio
    );
    ExitCode::SUCCESS
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn meminfo_kib() {
        let x = parse_meminfo("MemTotal:       123 kB\nSwapFree: 2 kB\n");
        assert_eq!(value(&x, "MemTotal"), 125952);
        assert_eq!(value(&x, "SwapFree"), 2048);
    }
    #[test]
    fn arcstats_header_ignored() {
        let x = parse_arcstats("13 1 0x01\nname type data\nhits 4 100\nmisses 4 10\n");
        assert_eq!(value(&x, "hits"), 100);
        assert_eq!(value(&x, "misses"), 10);
    }
}
