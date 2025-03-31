import javax.swing.*; 
import java.awt.*; 
import java.awt.event.*;

public class ShimejiClone extends JFrame { private JLabel shimejiLabel; private int x, y; private Timer timer;

public ShimejiClone() {
    setUndecorated(true);
    setBackground(new Color(0, 0, 0, 0));
    setAlwaysOnTop(true);

    ImageIcon shimejiIcon = new ImageIcon("dodo.png");
    shimejiLabel = new JLabel(shimejiIcon);
    add(shimejiLabel);

    pack();
    x = 100;
    y = 100;
    setLocation(x, y);
    
    shimejiLabel.addMouseListener(new MouseAdapter() {
        public void mousePressed(MouseEvent e) {
            x = e.getXOnScreen() - getWidth() / 2;
            y = e.getYOnScreen() - getHeight() / 2;
            setLocation(x, y);
        }
    });

    timer = new Timer(50, e -> moveShimeji());
    timer.start();
}

private void moveShimeji() {
    y += 1; // Simple gravity effect
    setLocation(x, y);
}

public static void main(String[] args) {
    SwingUtilities.invokeLater(() -> {
        new ShimejiClone().setVisible(true);
    });
}

}