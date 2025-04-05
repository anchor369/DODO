import javax.swing.*; 
import java.awt.*;
import java.awt.event.*;

public class ShimejiClone extends JFrame {
    private JLabel shimejiLabel;
    private Point dragOffset;

    public ShimejiClone() {
        setUndecorated(true);
        setBackground(new Color(0, 0, 0, 0));
        setAlwaysOnTop(true);

        // Load your image
        ImageIcon shimejiIcon = new ImageIcon("dodo1.png");
        shimejiLabel = new JLabel(shimejiIcon);
        add(shimejiLabel);

        pack();
        
        // Initial position
        setLocation(100, 100);
        
        // Mouse listeners for dragging anywhere
        MouseAdapter mouseAdapter = new MouseAdapter() {
            public void mousePressed(MouseEvent e) {
                // Store the offset between mouse position and frame corner
                dragOffset = new Point(e.getX(), e.getY());
            }
            
            public void mouseDragged(MouseEvent e) {
                // Calculate new position based on mouse position and offset
                Point currentScreen = e.getLocationOnScreen();
                setLocation(
                    currentScreen.x - dragOffset.x,
                    currentScreen.y - dragOffset.y
                );
            }
        };
        
        // Add listeners to the label
        shimejiLabel.addMouseListener(mouseAdapter);
        shimejiLabel.addMouseMotionListener(mouseAdapter);
        
        // Add a system tray icon to allow closing the application
        setupSystemTray();
    }
    
    private void setupSystemTray() {
        if (SystemTray.isSupported()) {
            try {
                SystemTray tray = SystemTray.getSystemTray();
                Image image = new ImageIcon("dodo.png").getImage()
                    .getScaledInstance(16, 16, Image.SCALE_SMOOTH);
                
                PopupMenu popup = new PopupMenu();
                MenuItem exitItem = new MenuItem("Exit");
                exitItem.addActionListener(e -> System.exit(0));
                popup.add(exitItem);
                
                TrayIcon trayIcon = new TrayIcon(image, "Shimeji Clone", popup);
                trayIcon.setImageAutoSize(true);
                tray.add(trayIcon);
            } catch (Exception e) {
                System.err.println("System tray error: " + e.getMessage());
            }
        }
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            new ShimejiClone().setVisible(true);
        });
    }
}
