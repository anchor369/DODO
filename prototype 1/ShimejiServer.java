import java.io.*;
import java.net.*;
import java.util.*;

public class ShimejiServer {
    private static final int PORT = 9876;
    private static Map<String, Socket> connectedClients = new HashMap<>();
    
    public static void main(String[] args) {
        try (ServerSocket serverSocket = new ServerSocket(PORT)) {
            System.out.println("Shimeji Server running on port " + PORT);
            
            // Thread to accept client connections
            new Thread(() -> {
                while (true) {
                    try {
                        Socket clientSocket = serverSocket.accept();
                        BufferedReader reader = new BufferedReader(new InputStreamReader(clientSocket.getInputStream()));
                        String clientId = reader.readLine();
                        
                        // Store client connection
                        connectedClients.put(clientId, clientSocket);
                        System.out.println("Client connected: " + clientId);
                        
                        // Handle disconnections
                        new Thread(() -> {
                            try {
                                // This will block until client disconnects
                                reader.readLine();
                            } catch (IOException e) {
                                // Client disconnected
                                connectedClients.remove(clientId);
                                System.out.println("Client disconnected: " + clientId);
                            }
                        }).start();
                        
                    } catch (IOException e) {
                        e.printStackTrace();
                    }
                }
            }).start();
            
            // Command interface
            Scanner scanner = new Scanner(System.in);
            while (true) {
                System.out.println("\nAvailable clients: " + String.join(", ", connectedClients.keySet()));
                System.out.println("Enter command (launch <clientId> OR list):");
                String command = scanner.nextLine();
                
                if (command.equals("list")) {
                    System.out.println("Connected clients: " + String.join(", ", connectedClients.keySet()));
                } else if (command.startsWith("launch ")) {
                    String[] parts = command.split(" ", 2);
                    if (parts.length == 2) {
                        String clientId = parts[1];
                        launchShimejiOnClient(clientId);
                    } else {
                        System.out.println("Invalid command format. Use: launch <clientId>");
                    }
                }
            }
            
        } catch (IOException e) {
            e.printStackTrace();
        }
    }
    
    private static void launchShimejiOnClient(String clientId) {
        Socket clientSocket = connectedClients.get(clientId);
        if (clientSocket == null) {
            System.out.println("Client not connected: " + clientId);
            return;
        }
        
        try {
            // Send command to launch Shimeji
            PrintWriter writer = new PrintWriter(clientSocket.getOutputStream(), true);
            writer.println("LAUNCH_SHIMEJI");
            
            System.out.println("Launch command sent to client: " + clientId);
            
        } catch (IOException e) {
            System.out.println("Error sending command to client: " + e.getMessage());
            connectedClients.remove(clientId);
        }
    }
}
