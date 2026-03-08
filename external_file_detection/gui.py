"""GUI application for External File Detection.

Inspired by ParquetViewer, this provides a user-friendly interface for:
- Selecting files or folders
- Previewing file metadata 
- Generating T-SQL DDL statements
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
from typing import Dict, List, Any, Optional
from pathlib import Path

from .external_file_detector import ExternalFileDetectorApp
from .file_detector import FileDetector


class ExternalFileDetectionGUI:
    """Main GUI application for External File Detection."""
    
    def __init__(self, root: tk.Tk):
        """Initialize the GUI application."""
        self.root = root
        self.app = ExternalFileDetectorApp()
        self.file_detector = FileDetector()
        
        # Current data
        self.current_files: List[Dict[str, Any]] = []
        self.selected_file_data: Optional[Dict[str, Any]] = None
        
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the user interface."""
        self.root.title("External File Detection Tool")
        self.root.geometry("1200x800")
        
        # Create main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Top toolbar
        self.create_toolbar(main_frame)
        
        # Main content area with splitter
        self.create_main_content(main_frame)
        
        # Status bar
        self.create_status_bar(main_frame)
        
    def create_toolbar(self, parent):
        """Create the toolbar with file/folder selection buttons."""
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=tk.X, pady=(0, 10))
        
        # File selection buttons
        ttk.Button(
            toolbar, 
            text="Select Files", 
            command=self.select_files
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            toolbar, 
            text="Select Folder", 
            command=self.select_folder
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        # Data source input
        ttk.Label(toolbar, text="Data Source:").pack(side=tk.LEFT, padx=(10, 5))
        self.data_source_var = tk.StringVar(value="MyDataSource")
        data_source_entry = ttk.Entry(toolbar, textvariable=self.data_source_var, width=15)
        data_source_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        # Clear button
        ttk.Button(
            toolbar, 
            text="Clear", 
            command=self.clear_files
        ).pack(side=tk.RIGHT)
        
    def create_main_content(self, parent):
        """Create the main content area with file list and preview."""
        # Create paned window for resizable sections
        paned_window = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)
        
        # Left panel - File list
        self.create_file_list_panel(paned_window)
        
        # Right panel - File details and SQL DDL
        self.create_details_panel(paned_window)
        
    def create_file_list_panel(self, parent):
        """Create the file list panel."""
        left_frame = ttk.Frame(parent)
        parent.add(left_frame, weight=1)
        
        # File list header
        ttk.Label(left_frame, text="Files", font=("TkDefaultFont", 12, "bold")).pack(anchor=tk.W, pady=(0, 5))
        
        # Treeview for file list
        columns = ("Name", "Type", "Size", "Status")
        self.file_tree = ttk.Treeview(left_frame, columns=columns, show="tree headings", height=15)
        
        # Configure columns
        self.file_tree.heading("#0", text="Path", anchor=tk.W)
        self.file_tree.column("#0", width=200)
        
        for col in columns:
            self.file_tree.heading(col, text=col, anchor=tk.W)
            self.file_tree.column(col, width=80)
        
        # Scrollbar for treeview
        tree_scroll = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=tree_scroll.set)
        
        # Pack treeview and scrollbar
        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind selection event
        self.file_tree.bind("<<TreeviewSelect>>", self.on_file_select)
        
    def create_details_panel(self, parent):
        """Create the file details and SQL DDL panel."""
        right_frame = ttk.Frame(parent)
        parent.add(right_frame, weight=2)
        
        # Create notebook for tabs
        notebook = ttk.Notebook(right_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # File Preview tab
        self.create_preview_tab(notebook)
        
        # SQL DDL tab
        self.create_sql_tab(notebook)
        
        # File Details tab
        self.create_details_tab(notebook)
        
    def create_preview_tab(self, notebook):
        """Create the file preview tab."""
        preview_frame = ttk.Frame(notebook)
        notebook.add(preview_frame, text="Preview")
        
        # Preview header
        self.preview_label = ttk.Label(preview_frame, text="Select a file to see preview", 
                                      font=("TkDefaultFont", 11, "bold"))
        self.preview_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Preview content (scrollable text)
        self.preview_text = scrolledtext.ScrolledText(preview_frame, height=20)
        self.preview_text.pack(fill=tk.BOTH, expand=True)
        
    def create_sql_tab(self, notebook):
        """Create the SQL DDL tab."""
        sql_frame = ttk.Frame(notebook)
        notebook.add(sql_frame, text="T-SQL DDL")
        
        # SQL header with copy button
        sql_header = ttk.Frame(sql_frame)
        sql_header.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(sql_header, text="Generated T-SQL DDL", 
                 font=("TkDefaultFont", 11, "bold")).pack(side=tk.LEFT)
        
        ttk.Button(sql_header, text="Copy to Clipboard", 
                  command=self.copy_sql_to_clipboard).pack(side=tk.RIGHT)
        
        # SQL content (scrollable text)
        self.sql_text = scrolledtext.ScrolledText(sql_frame, height=20, font=("Consolas", 10))
        self.sql_text.pack(fill=tk.BOTH, expand=True)
        
    def create_details_tab(self, notebook):
        """Create the file details tab."""
        details_frame = ttk.Frame(notebook)
        notebook.add(details_frame, text="Details")
        
        # Details content (scrollable text)
        self.details_text = scrolledtext.ScrolledText(details_frame, height=20)
        self.details_text.pack(fill=tk.BOTH, expand=True)
        
    def create_status_bar(self, parent):
        """Create the status bar."""
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(parent, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=(5, 0))
        
    def select_files(self):
        """Handle file selection."""
        filetypes = [
            ("All Supported", "*.csv;*.json;*.parquet;*.txt;*.orc;*.rc;*.delta"),
            ("CSV files", "*.csv"),
            ("JSON files", "*.json"), 
            ("Parquet files", "*.parquet"),
            ("Text files", "*.txt"),
            ("All files", "*.*")
        ]
        
        files = filedialog.askopenfilenames(
            title="Select Files to Analyze",
            filetypes=filetypes
        )
        
        if files:
            self.analyze_files(list(files))
            
    def select_folder(self):
        """Handle folder selection."""
        folder = filedialog.askdirectory(title="Select Folder to Analyze")
        
        if folder:
            self.analyze_folder(folder)
            
    def analyze_files(self, file_paths: List[str]):
        """Analyze selected files."""
        try:
            self.status_var.set("Analyzing files...")
            self.root.update()
            
            # Clear current data
            self.current_files = []
            self.clear_displays()
            
            # Analyze each file
            for file_path in file_paths:
                try:
                    metadata = self.file_detector.analyze_file_metadata(file_path)
                    self.current_files.append(metadata)
                except Exception as e:
                    # Add error entry
                    error_metadata = {
                        'file_path': file_path,
                        'file_type': 'error',
                        'file_size': 0,
                        'error': str(e)
                    }
                    self.current_files.append(error_metadata)
            
            # Update UI
            self.update_file_list()
            self.status_var.set(f"Analyzed {len(file_paths)} files")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to analyze files: {str(e)}")
            self.status_var.set("Error occurred")
            
    def analyze_folder(self, folder_path: str):
        """Analyze all supported files in a folder."""
        try:
            self.status_var.set("Scanning folder...")
            self.root.update()
            
            # Clear current data
            self.current_files = []
            self.clear_displays()
            
            # Scan directory
            self.current_files = self.file_detector.scan_directory(folder_path)
            
            # Update UI
            self.update_file_list()
            self.status_var.set(f"Found {len(self.current_files)} supported files")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to scan folder: {str(e)}")
            self.status_var.set("Error occurred")
            
    def update_file_list(self):
        """Update the file list display."""
        # Clear existing items
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
            
        # Add files to tree
        for file_data in self.current_files:
            file_path = file_data['file_path']
            file_name = os.path.basename(file_path)
            file_type = file_data.get('file_type', 'unknown')
            file_size = self.format_file_size(file_data.get('file_size', 0))
            status = "Error" if 'error' in file_data else "Ready"
            
            self.file_tree.insert("", tk.END, text=file_path, 
                                 values=(file_name, file_type, file_size, status))
                                 
    def format_file_size(self, size_bytes: int) -> str:
        """Format file size in human readable format."""
        if size_bytes == 0:
            return "0 B"
        
        units = ['B', 'KB', 'MB', 'GB']
        i = 0
        while size_bytes >= 1024 and i < len(units) - 1:
            size_bytes /= 1024
            i += 1
            
        return f"{size_bytes:.1f} {units[i]}"
        
    def on_file_select(self, event):
        """Handle file selection in the tree."""
        selection = self.file_tree.selection()
        if not selection:
            return
            
        # Get selected item
        item = selection[0]
        file_path = self.file_tree.item(item, "text")
        
        # Find matching file data
        self.selected_file_data = None
        for file_data in self.current_files:
            if file_data['file_path'] == file_path:
                self.selected_file_data = file_data
                break
                
        if self.selected_file_data:
            self.update_file_preview()
            
    def update_file_preview(self):
        """Update the file preview and details."""
        if not self.selected_file_data:
            return
            
        file_data = self.selected_file_data
        file_path = file_data['file_path']
        
        # Update preview tab
        self.update_preview_content(file_data)
        
        # Update SQL DDL tab
        self.update_sql_content(file_data)
        
        # Update details tab
        self.update_details_content(file_data)
        
    def update_preview_content(self, file_data: Dict[str, Any]):
        """Update the preview content."""
        file_path = file_data['file_path']
        file_name = os.path.basename(file_path)
        
        self.preview_label.config(text=f"Preview: {file_name}")
        self.preview_text.delete(1.0, tk.END)
        
        # Handle error case
        if 'error' in file_data:
            self.preview_text.insert(tk.END, f"Error analyzing file: {file_data['error']}")
            return
            
        try:
            # Show file preview based on type
            file_type = file_data.get('file_type', 'unknown')
            
            if file_type in ['csv', 'txt', 'json']:
                # Show text preview
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    # Read first 50 lines or 5KB, whichever is smaller
                    content = []
                    for i, line in enumerate(f):
                        if i >= 50:
                            content.append("... (truncated)")
                            break
                        content.append(line.rstrip())
                        if len(''.join(content)) > 5000:
                            content.append("... (truncated)")
                            break
                    
                    self.preview_text.insert(tk.END, '\n'.join(content))
                    
            elif file_type == 'parquet':
                # Show parquet metadata
                try:
                    import pyarrow.parquet as pq
                    parquet_file = pq.ParquetFile(file_path)
                    
                    preview_content = []
                    preview_content.append(f"Parquet File: {file_name}")
                    preview_content.append(f"Rows: {parquet_file.metadata.num_rows:,}")
                    preview_content.append(f"Columns: {len(parquet_file.schema)}")
                    preview_content.append("")
                    preview_content.append("Schema:")
                    for field in parquet_file.schema:
                        preview_content.append(f"  {field.name}: {field.type}")
                    
                    # Show sample data if possible
                    try:
                        table = parquet_file.read()
                        df = table.to_pandas().head(10)
                        preview_content.append("")
                        preview_content.append("Sample Data (first 10 rows):")
                        preview_content.append(df.to_string())
                    except Exception:
                        preview_content.append("")
                        preview_content.append("Could not load sample data")
                    
                    self.preview_text.insert(tk.END, '\n'.join(preview_content))
                    
                except Exception as e:
                    self.preview_text.insert(tk.END, f"Error reading Parquet file: {str(e)}")
                    
            else:
                self.preview_text.insert(tk.END, f"Preview not available for {file_type} files")
                
        except Exception as e:
            self.preview_text.insert(tk.END, f"Error loading preview: {str(e)}")
            
    def update_sql_content(self, file_data: Dict[str, Any]):
        """Update the SQL DDL content."""
        self.sql_text.delete(1.0, tk.END)
        
        # Handle error case
        if 'error' in file_data:
            self.sql_text.insert(tk.END, f"-- Cannot generate SQL DDL\n-- Error: {file_data['error']}")
            return
            
        try:
            # Generate SQL DDL
            data_source = self.data_source_var.get().strip() or "MyDataSource"
            sql_ddl = self.app.sql_generator.generate_complete_ddl(
                file_data, 
                data_source=data_source,
                location=os.path.basename(file_data['file_path'])
            )
            
            self.sql_text.insert(tk.END, sql_ddl)
            
        except Exception as e:
            self.sql_text.insert(tk.END, f"-- Error generating SQL DDL: {str(e)}")
            
    def update_details_content(self, file_data: Dict[str, Any]):
        """Update the file details content."""
        self.details_text.delete(1.0, tk.END)
        
        # Format file metadata for display
        details = []
        details.append(f"File Path: {file_data['file_path']}")
        details.append(f"File Type: {file_data.get('file_type', 'unknown')}")
        details.append(f"File Size: {self.format_file_size(file_data.get('file_size', 0))}")
        
        # Add metadata details
        if 'row_count' in file_data and file_data['row_count'] is not None:
            details.append(f"Rows: {file_data['row_count']:,}")
            
        if 'column_count' in file_data and file_data['column_count'] is not None:
            details.append(f"Columns: {file_data['column_count']}")
            
        if 'delimiter' in file_data and file_data['delimiter']:
            details.append(f"Delimiter: '{file_data['delimiter']}'")
            
        if 'encoding' in file_data and file_data['encoding']:
            details.append(f"Encoding: {file_data['encoding']}")
            
        if 'has_header' in file_data:
            details.append(f"Has Header: {file_data['has_header']}")
            
        if 'compression' in file_data and file_data['compression']:
            details.append(f"Compression: {file_data['compression']}")
            
        # Add schema information
        if 'schema' in file_data and file_data['schema']:
            details.append("")
            details.append("Schema:")
            for col_name, col_type in file_data['schema']:
                details.append(f"  {col_name}: {col_type}")
                
        # Add error information
        if 'error' in file_data:
            details.append("")
            details.append(f"Error: {file_data['error']}")
            
        self.details_text.insert(tk.END, '\n'.join(details))
        
    def copy_sql_to_clipboard(self):
        """Copy the SQL DDL to clipboard."""
        sql_content = self.sql_text.get(1.0, tk.END).strip()
        if sql_content:
            self.root.clipboard_clear()
            self.root.clipboard_append(sql_content)
            self.status_var.set("SQL DDL copied to clipboard")
        else:
            self.status_var.set("No SQL DDL to copy")
            
    def clear_files(self):
        """Clear all files and displays."""
        self.current_files = []
        self.selected_file_data = None
        self.clear_displays()
        self.update_file_list()
        self.status_var.set("Cleared")
        
    def clear_displays(self):
        """Clear all display areas."""
        self.preview_label.config(text="Select a file to see preview")
        self.preview_text.delete(1.0, tk.END)
        self.sql_text.delete(1.0, tk.END)
        self.details_text.delete(1.0, tk.END)


def main():
    """Run the GUI application."""
    root = tk.Tk()
    app = ExternalFileDetectionGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()