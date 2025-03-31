import sys
import random
import pygame
from pygame.locals import *

class DesktopAvatar:
    def __init__(self):
        # Initialize pygame
        pygame.init()
        
        # Set up the window to be transparent and always on top
        self.screen_width, self.screen_height = pygame.display.Info().current_w, pygame.display.Info().current_h
        self.window = pygame.display.set_mode((200, 200), pygame.NOFRAME | pygame.SRCALPHA)
        pygame.display.set_caption('Desktop Avatar')
        
        # Set the window to be always on top and clickthrough
        if sys.platform == 'win32':
            import ctypes
            hwnd = pygame.display.get_wm_info()['window']
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x00000008 | 0x00000020)
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        
        # Load avatar images for different states
        self.images = {
            'idle': [pygame.image.load('idel1.jpg').convert_alpha(), 
                    pygame.image.load('idel1.jpg').convert_alpha()],
            'walk': [pygame.image.load('idel1.jpg').convert_alpha(),
                    pygame.image.load('idel1.jpg').convert_alpha(),
                    pygame.image.load('idel1.jpg').convert_alpha(),
                    pygame.image.load('idel1.jpg').convert_alpha()],
            'sit': [pygame.image.load('idel1.jpg').convert_alpha()],
            'sleep': [pygame.image.load('idel1.jpg').convert_alpha()]
        }
        
        # Since we don't have actual images, we'll create placeholders
        for state in self.images:
            for i in range(len(self.images[state])):
                self.images[state][i] = self.create_placeholder_image(state)
        
        # Avatar state
        self.state = 'idle'
        self.frame_index = 0
        self.frame_count = 0
        self.frame_delay = 10
        
        # Avatar position and movement
        self.x = random.randint(0, self.screen_width - 100)
        self.y = 0
        self.vx = 0
        self.vy = 0
        self.direction = 1  # 1 for right, -1 for left
        self.is_dragging = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0
        
        # Behavior timers
        self.action_timer = 0
        self.action_change = random.randint(100, 300)
        
        # Main surface
        self.surface = pygame.Surface((100, 100), pygame.SRCALPHA)
        
        # Clock for controlling frame rate
        self.clock = pygame.time.Clock()
    
    def create_placeholder_image(self, state):
        """Create a placeholder image for testing"""
        surface = pygame.Surface((100, 100), pygame.SRCALPHA)
        
        # Draw different shapes based on state
        if state == 'idle':
            pygame.draw.circle(surface, (100, 200, 100, 200), (50, 50), 40)
            pygame.draw.circle(surface, (0, 0, 0, 200), (35, 40), 5)
            pygame.draw.circle(surface, (0, 0, 0, 200), (65, 40), 5)
            pygame.draw.arc(surface, (0, 0, 0, 200), (35, 50, 30, 20), 0, 3.14, 2)
        elif state == 'walk':
            pygame.draw.circle(surface, (100, 200, 100, 200), (50, 50), 40)
            pygame.draw.circle(surface, (0, 0, 0, 200), (35, 40), 5)
            pygame.draw.circle(surface, (0, 0, 0, 200), (65, 40), 5)
            pygame.draw.arc(surface, (0, 0, 0, 200), (35, 50, 30, 20), 0, 3.14, 2)
            # Add little feet
            pygame.draw.ellipse(surface, (100, 100, 100, 200), (35, 85, 15, 10))
            pygame.draw.ellipse(surface, (100, 100, 100, 200), (55, 85, 15, 10))
        elif state == 'sit':
            pygame.draw.ellipse(surface, (100, 200, 100, 200), (20, 40, 60, 50))
            pygame.draw.circle(surface, (0, 0, 0, 200), (35, 50), 4)
            pygame.draw.circle(surface, (0, 0, 0, 200), (55, 50), 4)
            pygame.draw.arc(surface, (0, 0, 0, 200), (35, 60, 20, 10), 0, 3.14, 2)
        elif state == 'sleep':
            pygame.draw.ellipse(surface, (100, 200, 100, 200), (20, 60, 60, 30))
            pygame.draw.lines(surface, (0, 0, 0, 200), False, [(35, 70), (45, 70), (55, 70)], 2)
            # Zzz
            pygame.draw.line(surface, (0, 0, 0, 200), (70, 40), (80, 30), 2)
            pygame.draw.line(surface, (0, 0, 0, 200), (80, 30), (90, 40), 2)
        
        return surface
    
    def update(self):
        # Update animation frame
        self.frame_count += 1
        if self.frame_count >= self.frame_delay:
            self.frame_count = 0
            self.frame_index = (self.frame_index + 1) % len(self.images[self.state])
        
        # Update position if not being dragged
        if not self.is_dragging:
            self.x += self.vx * self.direction
            self.y += self.vy
            
            # Boundary check
            if self.x < 0:
                self.x = 0
                self.direction = 1
            elif self.x > self.screen_width - 100:
                self.x = self.screen_width - 100
                self.direction = -1
            
            # Gravity effect - fall until hitting bottom of screen
            if self.y < self.screen_height - 100:
                self.vy += 0.5
            else:
                self.y = self.screen_height - 100
                self.vy = 0
                
                # If we just landed, we might sit
                if self.state == 'walk':
                    if random.random() < 0.3:
                        self.set_state('sit')
            
            # Update action timer and possibly change state
            self.action_timer += 1
            if self.action_timer >= self.action_change:
                self.action_timer = 0
                self.action_change = random.randint(100, 300)
                self.choose_random_action()
        
    def choose_random_action(self):
        # Only change actions if we're not in a restricted state (like falling)
        if self.y >= self.screen_height - 100:  # If we're on the ground
            r = random.random()
            if r < 0.4:
                self.set_state('idle')
                self.vx = 0
            elif r < 0.7:
                self.set_state('walk')
                self.vx = random.uniform(1, 3)
            elif r < 0.9:
                self.set_state('sit')
                self.vx = 0
            else:
                self.set_state('sleep')
                self.vx = 0
    
    def set_state(self, state):
        self.state = state
        self.frame_index = 0
        self.frame_count = 0
    
    def draw(self):
        # Clear the window
        self.window.fill((0, 0, 0, 0))
        
        # Create a temporary surface with the current frame
        current_frame = self.images[self.state][self.frame_index]
        
        # If facing left, flip the image
        if self.direction == -1:
            current_frame = pygame.transform.flip(current_frame, True, False)
        
        # Draw the avatar on the window
        self.window.blit(current_frame, (0, 0))
        
        # Update the display
        pygame.display.update()
    
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == QUIT:
                return False
            
            # Right-click to show menu
            elif event.type == MOUSEBUTTONDOWN and event.button == 3:
                self.show_context_menu()
            
            # Left-click to drag
            elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                mouse_x, mouse_y = event.pos
                if self.is_click_on_avatar(mouse_x, mouse_y):
                    self.is_dragging = True
                    self.drag_offset_x = mouse_x
                    self.drag_offset_y = mouse_y
            
            # Release to drop
            elif event.type == MOUSEBUTTONUP and event.button == 1:
                self.is_dragging = False
            
            # Drag movement
            elif event.type == MOUSEMOTION and self.is_dragging:
                mouse_x, mouse_y = event.pos
                self.x += mouse_x - self.drag_offset_x
                self.y += mouse_y - self.drag_offset_y
                self.drag_offset_x = mouse_x
                self.drag_offset_y = mouse_y
                
                # Boundary check
                self.x = max(0, min(self.x, self.screen_width - 100))
                self.y = max(0, min(self.y, self.screen_height - 100))
        
        return True
    
    def is_click_on_avatar(self, mouse_x, mouse_y):
        # Simple rectangular hit detection
        return (self.x <= mouse_x <= self.x + 100 and 
                self.y <= mouse_y <= self.y + 100)
    
    def show_context_menu(self):
        # Create a small menu surface
        menu = pygame.Surface((120, 100), pygame.SRCALPHA)
        menu.fill((200, 200, 200, 200))
        
        # Menu options
        options = ["Idle", "Walk", "Sit", "Sleep", "Exit"]
        font = pygame.font.SysFont(None, 20)
        
        for i, option in enumerate(options):
            text = font.render(option, True, (0, 0, 0))
            menu.blit(text, (10, 10 + i * 20))
        
        # Display menu
        menu_x = min(self.x, self.screen_width - 120)
        menu_y = min(self.y, self.screen_height - 100)
        self.window.blit(menu, (menu_x, menu_y))
        pygame.display.update()
        
        # Wait for menu selection
        waiting_for_selection = True
        while waiting_for_selection:
            for event in pygame.event.get():
                if event.type == QUIT:
                    return False
                elif event.type == MOUSEBUTTONDOWN:
                    mouse_x, mouse_y = event.pos
                    if (menu_x <= mouse_x <= menu_x + 120 and 
                        menu_y <= mouse_y <= menu_y + 100):
                        option_idx = (mouse_y - menu_y - 10) // 20
                        if 0 <= option_idx < len(options):
                            if options[option_idx] == "Exit":
                                return False
                            elif options[option_idx] == "Idle":
                                self.set_state('idle')
                                self.vx = 0
                            elif options[option_idx] == "Walk":
                                self.set_state('walk')
                                self.vx = random.uniform(1, 3)
                            elif options[option_idx] == "Sit":
                                self.set_state('sit')
                                self.vx = 0
                            elif options[option_idx] == "Sleep":
                                self.set_state('sleep')
                                self.vx = 0
                    waiting_for_selection = False
        return True
    
    def run(self):
        running = True
        while running:
            # Process events
            running = self.handle_events()
            
            # Update avatar state
            self.update()
            
            # Draw the avatar
            self.draw()
            
            # Cap the frame rate
            self.clock.tick(60)
        
        pygame.quit()
        sys.exit()

def create_exe():
    """
    Information about creating the executable.
    This is not actual code but a guide for how to package the app.
    """
    # To create an executable from this Python script:
    # 1. Install PyInstaller: pip install pyinstaller
    # 2. Run PyInstaller: pyinstaller --onefile --windowed desktop_avatar.py
    # 3. The executable will be created in the 'dist' folder
    # 4. Make sure to include any image assets in the same folder as the executable
    pass

if __name__ == "__main__":
    # Create and run the desktop avatar
    avatar = DesktopAvatar()
    avatar.run()
