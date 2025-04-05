import java.io.*;
import java.net.*;

public class ShimejiClient {
    private static final String SERVER_IP = "192.168.159.63"; // Replace with your Raspberry Pi IP
    private static final int SERVER_PORT = 9876;
    
    public static void main(String[] args) {
        if (args.length != 1) {
            System.out.println("Usage: java ShimejiClient <clientId>");
            return;
        }
        
        String clientId = args[0];
        
        try {
            Socket socket = new Socket(SERVER_IP, SERVER_PORT);
            
            // Send client ID to server
            PrintWriter writer = new PrintWriter(socket.getOutputStream(), true);
            writer.println(clientId);
            
            System.out.println("Connected to server as client: " + clientId);
            
            // Listen for commands from server
            BufferedReader reader = new BufferedReader(new InputStreamReader(socket.getInputStream()));
            while (true) {
                String command = reader.readLine();
                
                if (command == null) {
                    // Server disconnected
                    break;
                }
                
                if (command.equals("LAUNCH_SHIMEJI")) {
                    System.out.println("Launching Shimeji application...");
                    launchShimeji();
                }
            }
            
        } catch (IOException e) {
            System.out.println("Error connecting to server: " + e.getMessage());
        }
    }
    
    private static void launchShimeji() {
        try {
            // Launch the ShimejiClone application
            ProcessBuilder processBuilder = new ProcessBuilder("java", "ShimejiClone");
            processBuilder.inheritIO(); // Redirect output to console for debugging
            Process process = processBuilder.start();
            
            // Optional: You can wait for the process to complete if needed
            // process.waitFor();
            
        } catch (IOException e) {
            System.out.println("Error launching Shimeji: " + e.getMessage());
        }
    }
}
