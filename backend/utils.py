def format_bytes(bytes_value: int) -> str:
    """Convert bytes to human-readable format (e.g., 1024 -> '1.0 KB')"""
    if bytes_value == 0:
        return "0 B"
    
    # Define units in order
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    
    # Find the appropriate unit
    size = float(bytes_value)
    unit_index = 0
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    # Format the number
    if size >= 100:
        return f"{size:.0f} {units[unit_index]}"
    if size >= 10:
        return f"{size:.1f} {units[unit_index]}"
    return f"{size:.2f} {units[unit_index]}"


def format_bytes_short(bytes_value: int) -> str:
    """Convert bytes to short human-readable format (e.g., 1024 -> '1K')"""
    if bytes_value == 0:
        return "0"
    
    # Define short units
    units = ['', 'K', 'M', 'G', 'T', 'P']
    
    # Find the appropriate unit
    size = float(bytes_value)
    unit_index = 0
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    # Format the number
    if size >= 100:
        return f"{size:.0f}{units[unit_index]}"
    if size >= 10:
        return f"{size:.1f}{units[unit_index]}"
    return f"{size:.2f}{units[unit_index]}" 