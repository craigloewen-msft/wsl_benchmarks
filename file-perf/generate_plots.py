#!/usr/bin/env python3
"""
Generate performance comparison plots from benchmark JSON files.
"""

import json
import os
from pathlib import Path
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import numpy as np

# Configuration
GRAPH_DATA_FOLDER = "graph_data"
GRAPH_OUTPUT_FOLDER = "graph_output"

def load_json_files(folder_path):
    """Load all JSON files from the specified folder."""
    json_files = []
    folder = Path(folder_path)
    
    if not folder.exists():
        print(f"Warning: {folder_path} does not exist. Creating it...")
        folder.mkdir(parents=True, exist_ok=True)
        return json_files
    
    for file_path in folder.glob("*.json"):
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                json_files.append(data)
                print(f"Loaded: {file_path.name}")
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    
    return json_files

def extract_test_data(data, test_prefix, metric_key):
    """
    Extract test data for a specific test type and metric.
    
    Args:
        data: The JSON data dictionary
        test_prefix: Prefix of the test (e.g., 'seq_write_', 'rand_write_')
        metric_key: The metric to extract (e.g., 'speed_bytes_per_sec', 'iops')
    
    Returns:
        Dictionary mapping file_size to list of values
    """
    results = {}
    aggregated_stats = data.get('aggregated_statistics', {})
    
    for test_name, test_data in aggregated_stats.items():
        if test_name.startswith(test_prefix):
            # Get file size from test data if available
            file_size_data = test_data.get('file_size', {})
            if isinstance(file_size_data, dict) and file_size_data:
                file_size = file_size_data.get('mean', 0)
            else:
                # If not in data, extract from test name
                # Test name format: prefix_filesize (e.g., 'seq_write_10240')
                try:
                    file_size = int(test_name.replace(test_prefix, ''))
                except (ValueError, AttributeError):
                    print(f"Warning: Could not extract file size from test name: {test_name}")
                    continue
            
            # Get the metric values
            metric_data = test_data.get(metric_key, {})
            values = metric_data.get('values', [])
            
            if values and file_size > 0:
                results[int(file_size)] = values
            elif not values:
                print(f"Warning: No values found for {test_name} with metric {metric_key}")
    
    return results

def format_file_size(size_bytes):
    """
    Format file size in human-readable format.
    
    Args:
        size_bytes: Size in bytes
    
    Returns:
        Formatted string (e.g., '10 KB', '1 MB', '500 MB')
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes // 1024} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        mb = size_bytes / (1024 * 1024)
        if mb >= 100:
            return f"{int(mb)} MB"
        else:
            return f"{mb:.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

def extract_file_operation_data(data, operation_type, metric_key):
    """
    Extract file creation/deletion data.
    
    Args:
        data: The JSON data dictionary
        operation_type: 'file_creation' or 'file_deletion'
        metric_key: The metric to extract (e.g., 'files_per_sec')
    
    Returns:
        Dictionary with operation data
    """
    aggregated_stats = data.get('aggregated_statistics', {})
    operation_data = aggregated_stats.get(operation_type, {})
    
    if operation_data:
        num_files = operation_data.get('files_created' if operation_type == 'file_creation' else 'files_deleted', {}).get('mean', 0)
        metric_data = operation_data.get(metric_key, {})
        values = metric_data.get('values', [])
        
        if values:
            return {int(num_files): values}
    
    return {}

def create_box_plot(all_data, title, ylabel, xlabel, output_filename, format_x_as_filesize=False, show_median_values=True):
    """
    Create a violin plot from the data.

    Args:
        all_data: Dictionary mapping test_name -> {file_size/num_files: [values]}
        title: Plot title
        ylabel: Y-axis label
        xlabel: X-axis label
        output_filename: Output file path
        format_x_as_filesize: If True, format x-axis labels as file sizes
        show_median_values: If True, display median values on the plot
    """
    fig, ax = plt.subplots(figsize=(12, 7))

    # Get all unique x-positions (file_size or num_files) across all tests
    all_x_positions = set()
    for test_data in all_data.values():
        all_x_positions.update(test_data.keys())
    x_positions = sorted(all_x_positions)

    # Prepare data for plotting
    num_tests = len(all_data)
    colors = plt.cm.Set3(np.linspace(0, 1, num_tests))

    # Calculate positions for grouped violin plots
    width = 0.8 / num_tests  # Width of each violin
    offset_start = -(num_tests - 1) * width / 2

    # Sort test names alphabetically for consistent legend ordering
    legend_handles = []
    for idx, (test_name, test_data) in enumerate(sorted(all_data.items())):
        positions = []
        data_to_plot = []

        for x_pos in x_positions:
            if x_pos in test_data:
                # Offset position for this test
                positions.append(x_positions.index(x_pos) + offset_start + idx * width)
                data_to_plot.append(test_data[x_pos])

        if data_to_plot:
            # Create violin plot
            parts = ax.violinplot(data_to_plot, positions=positions, widths=width * 0.8,
                                  showmeans=True, showmedians=True)

            # Hide the violin bodies
            for pc in parts['bodies']:
                pc.set_alpha(0)

            # Color all statistical lines to match the legend color
            for partname in ('cbars', 'cmins', 'cmaxes', 'cmeans', 'cmedians'):
                if partname in parts:
                    parts[partname].set_edgecolor(colors[idx])
                    parts[partname].set_linewidth(2)

            # Add to legend (create a patch for the legend)
            from matplotlib.patches import Patch
            legend_handles.append(Patch(facecolor=colors[idx], alpha=0.7, edgecolor='black', label=test_name))

            # Add median values as text if requested
            if show_median_values:
                for pos, data in zip(positions, data_to_plot):
                    median = np.median(data)
                    ax.text(pos, median, f'{median:.1f}',
                           ha='center', va='bottom', fontsize=8, fontweight='bold')
    
    # Set labels and title
    ax.set_xlabel(xlabel, fontsize=12, fontweight='bold')
    ax.set_ylabel(ylabel, fontsize=12, fontweight='bold')
    ax.set_title(title, fontsize=14, fontweight='bold')

    # Set x-axis ticks
    ax.set_xticks(range(len(x_positions)))
    if format_x_as_filesize:
        ax.set_xticklabels([format_file_size(x) for x in x_positions], rotation=45, ha='right')
    else:
        ax.set_xticklabels([str(x) for x in x_positions])

    # Add legend
    if legend_handles:
        ax.legend(handles=legend_handles, loc='best', fontsize=10)
    
    # Add grid
    ax.grid(True, alpha=0.3, linestyle='--')
    
    # Tight layout
    plt.tight_layout()
    
    # Save the plot
    plt.savefig(output_filename, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_filename}")
    plt.close()

def create_simple_box_plot(all_data, title, ylabel, output_filename, show_median_values=True):
    """
    Create a simple violin plot with all data grouped by test name only.

    Args:
        all_data: Dictionary mapping test_name -> {file_size/num_files: [values]}
        title: Plot title
        ylabel: Y-axis label
        output_filename: Output file path
        show_median_values: If True, display median values on the plot
    """
    fig, ax = plt.subplots(figsize=(12, 7))

    # Prepare data for plotting - combine all values for each test
    num_tests = len(all_data)
    colors = plt.cm.Set3(np.linspace(0, 1, num_tests))

    positions = []
    data_to_plot = []
    test_labels = []

    # Sort test names alphabetically for consistent ordering
    for idx, (test_name, test_data) in enumerate(sorted(all_data.items())):
        # Combine all values across all x-positions (file sizes, etc.) for this test
        all_values = []
        for values_list in test_data.values():
            all_values.extend(values_list)

        if all_values:
            positions.append(idx)
            data_to_plot.append(all_values)
            test_labels.append(test_name)

    # Create violin plots
    if data_to_plot:
        parts = ax.violinplot(data_to_plot, positions=positions, widths=0.6,
                              showmeans=True, showmedians=True)

        # Hide each violin body
        for pc in parts['bodies']:
            pc.set_alpha(0)

        # Color all statistical lines to match their colors
        for partname in ('cbars', 'cmins', 'cmaxes', 'cmeans'):
            if partname in parts:
                parts[partname].set_edgecolors(colors)
                parts[partname].set_linewidth(2)

        # Make medians match the violin colors
        if 'cmedians' in parts:
            parts['cmedians'].set_edgecolors(colors)
            parts['cmedians'].set_linewidth(2)

        # Add median values as text if requested
        if show_median_values:
            for pos, data in zip(positions, data_to_plot):
                median = np.median(data)
                ax.text(pos, median, f'{median:.1f}',
                       ha='center', va='bottom', fontsize=8, fontweight='bold')
    
    # Set labels and title
    ax.set_ylabel(ylabel, fontsize=12, fontweight='bold')
    ax.set_title(title, fontsize=14, fontweight='bold')
    
    # Set x-axis ticks with test names
    ax.set_xticks(positions)
    ax.set_xticklabels(test_labels, rotation=45, ha='right')
    
    # Add grid
    ax.grid(True, alpha=0.3, linestyle='--', axis='y')
    
    # Tight layout
    plt.tight_layout()
    
    # Save the plot
    plt.savefig(output_filename, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_filename}")
    plt.close()

def main():
    """Main function to generate all plots."""
    # Create output folder if it doesn't exist
    output_folder = Path(GRAPH_OUTPUT_FOLDER)
    output_folder.mkdir(parents=True, exist_ok=True)
    
    # Load all JSON files
    print(f"\nLoading JSON files from {GRAPH_DATA_FOLDER}...")
    json_data_list = load_json_files(GRAPH_DATA_FOLDER)
    
    if not json_data_list:
        print(f"\nNo JSON files found in {GRAPH_DATA_FOLDER}/")
        print("Please add JSON benchmark files to this folder.")
        return
    
    print(f"\nLoaded {len(json_data_list)} JSON file(s)")
    print("\nGenerating plots...\n")
    
    # 1. Sequential Write Performance (MB/s)
    seq_write_data = {}
    for data in json_data_list:
        test_name = data.get('name', 'Unknown')
        # Convert bytes/sec to MB/sec
        raw_data = extract_test_data(data, 'seq_write_', 'speed_bytes_per_sec')
        seq_write_data[test_name] = {k: [v / (1024 * 1024) for v in vals] 
                                      for k, vals in raw_data.items()}
    
    create_box_plot(
        seq_write_data,
        "Sequential Write Performance",
        "Speed (MB/s)",
        "File Size",
        output_folder / "sequential_write_performance.png",
        format_x_as_filesize=True
    )
    
    # 2. Sequential Read Performance (MB/s)
    seq_read_data = {}
    for data in json_data_list:
        test_name = data.get('name', 'Unknown')
        # Convert bytes/sec to MB/sec
        raw_data = extract_test_data(data, 'seq_read_', 'speed_bytes_per_sec')
        seq_read_data[test_name] = {k: [v / (1024 * 1024) for v in vals] 
                                     for k, vals in raw_data.items()}
    
    create_box_plot(
        seq_read_data,
        "Sequential Read Performance",
        "Speed (MB/s)",
        "File Size",
        output_folder / "sequential_read_performance.png",
        format_x_as_filesize=True
    )
    
    # 3. Random Write Test (IOPS)
    rand_write_data = {}
    for data in json_data_list:
        test_name = data.get('name', 'Unknown')
        # For random write, extract file size from test name
        rand_write_data[test_name] = extract_test_data(data, 'rand_write_', 'iops')
    
    create_box_plot(
        rand_write_data,
        "Random Write Performance",
        "IOPS",
        "File Size",
        output_folder / "random_write_performance.png",
        format_x_as_filesize=True
    )
    
    # 4. Random Read Test (IOPS)
    rand_read_data = {}
    for data in json_data_list:
        test_name = data.get('name', 'Unknown')
        # For random read, extract file size from test name
        rand_read_data[test_name] = extract_test_data(data, 'rand_read_', 'iops')
    
    create_box_plot(
        rand_read_data,
        "Random Read Performance",
        "IOPS",
        "File Size",
        output_folder / "random_read_performance.png",
        format_x_as_filesize=True
    )
    
    # 5. File Creation Performance
    file_creation_data = {}
    for data in json_data_list:
        test_name = data.get('name', 'Unknown')
        file_creation_data[test_name] = extract_file_operation_data(data, 'file_creation', 'files_per_sec')
    
    create_box_plot(
        file_creation_data,
        "File Creation Performance",
        "Files per Second",
        "Number of Files Created",
        output_folder / "file_creation_performance.png"
    )
    
    # 6. File Deletion Performance
    file_deletion_data = {}
    for data in json_data_list:
        test_name = data.get('name', 'Unknown')
        file_deletion_data[test_name] = extract_file_operation_data(data, 'file_deletion', 'files_per_sec')
    
    create_box_plot(
        file_deletion_data,
        "File Deletion Performance",
        "Files per Second",
        "Number of Files Deleted",
        output_folder / "file_deletion_performance.png"
    )
    
    # 7. NPM Install Performance
    npm_install_data = {}
    for data in json_data_list:
        test_name = data.get('name', 'Unknown')
        aggregated_stats = data.get('aggregated_statistics', {})
        npm_data = aggregated_stats.get('npm_install', {})
        
        if npm_data:
            num_files = npm_data.get('files_created', {}).get('mean', 0)
            speed_data = npm_data.get('speed_bytes_per_sec', {})
            values = speed_data.get('values', [])
            
            if values:
                # Convert bytes/sec to MB/sec
                npm_install_data[test_name] = {int(num_files): [v / (1024 * 1024) for v in values]}
    
    create_simple_box_plot(
        npm_install_data,
        "NPM Install Performance",
        "Speed (MB/s)",
        output_folder / "npm_install_performance.png"
    )
    
    # 8. Pip Install Performance
    pip_install_data = {}
    for data in json_data_list:
        test_name = data.get('name', 'Unknown')
        aggregated_stats = data.get('aggregated_statistics', {})
        pip_data = aggregated_stats.get('pip_install', {})
        
        if pip_data:
            num_packages = pip_data.get('packages_installed', {}).get('mean', 0)
            speed_data = pip_data.get('speed_bytes_per_sec', {})
            values = speed_data.get('values', [])
            
            if values:
                # Convert bytes/sec to MB/sec
                pip_install_data[test_name] = {int(num_packages): [v / (1024 * 1024) for v in values]}
    
    create_simple_box_plot(
        pip_install_data,
        "Pip Install Performance",
        "Speed (MB/s)",
        output_folder / "pip_install_performance.png"
    )
    
    # 9. NPM Install Duration
    npm_install_duration_data = {}
    for data in json_data_list:
        test_name = data.get('name', 'Unknown')
        aggregated_stats = data.get('aggregated_statistics', {})
        npm_data = aggregated_stats.get('npm_install', {})
        
        if npm_data:
            num_files = npm_data.get('files_created', {}).get('mean', 0)
            duration_data = npm_data.get('duration_sec', {})
            values = duration_data.get('values', [])
            
            if values:
                npm_install_duration_data[test_name] = {int(num_files): values}
    
    create_simple_box_plot(
        npm_install_duration_data,
        "NPM Install Duration",
        "Duration (seconds)",
        output_folder / "npm_install_duration.png"
    )
    
    # 10. Pip Install Duration
    pip_install_duration_data = {}
    for data in json_data_list:
        test_name = data.get('name', 'Unknown')
        aggregated_stats = data.get('aggregated_statistics', {})
        pip_data = aggregated_stats.get('pip_install', {})
        
        if pip_data:
            num_packages = pip_data.get('packages_installed', {}).get('mean', 0)
            duration_data = pip_data.get('duration_sec', {})
            values = duration_data.get('values', [])
            
            if values:
                pip_install_duration_data[test_name] = {int(num_packages): values}
    
    create_simple_box_plot(
        pip_install_duration_data,
        "Pip Install Duration",
        "Duration (seconds)",
        output_folder / "pip_install_duration.png"
    )
    
    # 11. Git Clone Performance
    git_clone_data = {}
    for data in json_data_list:
        test_name = data.get('name', 'Unknown')
        aggregated_stats = data.get('aggregated_statistics', {})
        git_data = aggregated_stats.get('git_clone', {})
        
        if git_data:
            num_files = git_data.get('files_created', {}).get('mean', 0)
            speed_data = git_data.get('speed_bytes_per_sec', {})
            values = speed_data.get('values', [])
            
            if values:
                # Convert bytes/sec to MB/sec
                git_clone_data[test_name] = {int(num_files): [v / (1024 * 1024) for v in values]}
    
    create_simple_box_plot(
        git_clone_data,
        "Git Clone Performance",
        "Speed (MB/s)",
        output_folder / "git_clone_performance.png"
    )
    
    # 12. Git Clone Duration
    git_clone_duration_data = {}
    for data in json_data_list:
        test_name = data.get('name', 'Unknown')
        aggregated_stats = data.get('aggregated_statistics', {})
        git_data = aggregated_stats.get('git_clone', {})
        
        if git_data:
            num_files = git_data.get('files_created', {}).get('mean', 0)
            duration_data = git_data.get('duration_sec', {})
            values = duration_data.get('values', [])
            
            if values:
                git_clone_duration_data[test_name] = {int(num_files): values}
    
    create_simple_box_plot(
        git_clone_duration_data,
        "Git Clone Duration",
        "Duration (seconds)",
        output_folder / "git_clone_duration.png"
    )
    
    print("\n✓ All plots generated successfully!")
    print(f"  Output folder: {output_folder.absolute()}\n")

if __name__ == "__main__":
    main()
