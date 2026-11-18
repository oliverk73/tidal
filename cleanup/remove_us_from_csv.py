#!/usr/bin/env python3
"""
Remove US stations from CSV files used for name correction
"""
import csv
import sys

def remove_us_stations_from_csv(input_file, output_file, country_column_indices):
    """
    Remove US stations from a CSV file.

    Args:
        input_file: Path to input CSV
        output_file: Path to output CSV
        country_column_indices: List of column indices to check for "United States"
    """
    removed_count = 0
    kept_count = 0

    with open(input_file, 'r', encoding='iso-8859-1') as inf:
        with open(output_file, 'w', encoding='iso-8859-1', newline='') as outf:
            reader = csv.reader(inf, delimiter=';')
            writer = csv.writer(outf, delimiter=';', lineterminator='\r\n')

            # Read and write header
            header = next(reader)
            writer.writerow(header)

            # Process each row
            for row in reader:
                # Check if any of the country columns contains "United States"
                is_us_station = False
                for col_idx in country_column_indices:
                    if col_idx < len(row) and row[col_idx].strip() == 'United States':
                        is_us_station = True
                        break

                if is_us_station:
                    removed_count += 1
                else:
                    writer.writerow(row)
                    kept_count += 1

    print(f"  Removed: {removed_count}")
    print(f"  Kept: {kept_count}")
    return removed_count, kept_count

def main():
    files_to_process = [
        {
            'input': '/home/oliver/harmonics_working/station_name_corrections_iso8859.csv',
            'output': '/home/oliver/harmonics_working/station_name_corrections_iso8859_no_us.csv',
            'country_columns': [6, 12]  # Corrected_Country and possibly another country column
        },
        {
            'input': '/home/oliver/harmonics_working/station_name_corrections_final.csv',
            'output': '/home/oliver/harmonics_working/station_name_corrections_final_no_us.csv',
            'country_columns': [6, 12]
        },
        {
            'input': '/home/oliver/harmonics_working/stations_final_corrected.csv',
            'output': '/home/oliver/harmonics_working/stations_final_corrected_no_us.csv',
            'country_columns': [6, 12]
        },
        {
            'input': '/home/oliver/harmonics_working/stations_clean.csv',
            'output': '/home/oliver/harmonics_working/stations_clean_no_us.csv',
            'country_columns': [6]
        }
    ]

    for file_info in files_to_process:
        print(f"\nProcessing {file_info['input']}...")
        try:
            remove_us_stations_from_csv(
                file_info['input'],
                file_info['output'],
                file_info['country_columns']
            )
            print(f"Output written to: {file_info['output']}")
        except Exception as e:
            print(f"Error processing {file_info['input']}: {e}")

if __name__ == '__main__':
    main()
