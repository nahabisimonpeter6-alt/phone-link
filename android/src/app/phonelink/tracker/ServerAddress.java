package app.phonelink.tracker;

import java.net.InetAddress;
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

/** Validates a pairing origin without resolving hostnames or exposing pasted input in errors. */
final class ServerAddress {
    private static final String ADDRESS = "Enter only the server address, for example https://yourname.pythonanywhere.com or http://192.168.1.10:8080.";
    private static final String PHONE = "This address points to this phone, not your computer. Use your computer's Wi-Fi IP for local testing, or your hosted HTTPS website address.";

    private ServerAddress() { }

    static String normalize(String value) {
        String text = trimClipboardWhitespace(value == null ? "" : value);
        if (text.isEmpty()) throw new IllegalArgumentException(ADDRESS);
        for (int index = 0; index < text.length(); index++) {
            if (clipboardWhitespace(text.charAt(index))) {
                throw new IllegalArgumentException("Remove spaces inside the server address. Copy only its http:// or https:// website address.");
            }
        }
        final URI uri;
        try { uri = new URI(text); }
        catch (URISyntaxException ignored) { throw new IllegalArgumentException(ADDRESS); }
        String scheme = uri.getScheme();
        if (scheme == null || (!scheme.equalsIgnoreCase("http") && !scheme.equalsIgnoreCase("https"))) {
            throw new IllegalArgumentException("The server address must start with https:// (or http:// for local Wi-Fi).");
        }
        String host = uri.getHost();
        String path = uri.getRawPath();
        if (host == null || uri.getRawUserInfo() != null || uri.getRawQuery() != null || uri.getRawFragment() != null
                || (path != null && !path.isEmpty() && !path.equals("/"))) {
            throw new IllegalArgumentException(ADDRESS);
        }
        int port = uri.getPort();
        if (port == 0 || port > 65535 || uri.getRawAuthority().endsWith(":")) {
            throw new IllegalArgumentException("Use a server port between 1 and 65535, or leave the port out of an HTTPS website address.");
        }
        host = host.toLowerCase(Locale.ROOT);
        String localName = host;
        while (localName.endsWith(".")) localName = localName.substring(0, localName.length() - 1);
        if (localName.equals("localhost") || localName.endsWith(".localhost")) throw new IllegalArgumentException(PHONE);

        boolean privateIpv4 = false;
        if (host.matches("[0-9.]+")) {
            String[] parts = host.split("\\.", -1);
            if (parts.length != 4) {
                // These commonly used shorthand forms can resolve to loopback on different clients.
                if (host.equals("0") || host.equals("127") || host.equals("2130706433")) throw new IllegalArgumentException(PHONE);
                throw new IllegalArgumentException(ADDRESS);
            }
            int[] octets = new int[4];
            for (int index = 0; index < 4; index++) {
                if (parts[index].isEmpty() || parts[index].length() > 3
                        || (parts[index].length() > 1 && parts[index].startsWith("0"))) {
                    throw new IllegalArgumentException(ADDRESS);
                }
                octets[index] = Integer.parseInt(parts[index]);
                if (octets[index] > 255) throw new IllegalArgumentException(ADDRESS);
            }
            if (octets[0] == 127 || (octets[0] == 0 && octets[1] == 0 && octets[2] == 0 && octets[3] == 0)) {
                throw new IllegalArgumentException(PHONE);
            }
            privateIpv4 = octets[0] == 10 || (octets[0] == 172 && octets[1] >= 16 && octets[1] <= 31)
                || (octets[0] == 192 && octets[1] == 168);
        } else if (host.matches("(?:0x[0-9a-f]+|[0-9]+)(?:\\.(?:0x[0-9a-f]+|[0-9]+))*")) {
            // Reject legacy hex/octal-looking IPv4 spellings rather than relying on client-specific resolution.
            throw new IllegalArgumentException(ADDRESS);
        } else if (host.indexOf(':') >= 0) {
            // Only numeric IPv6 literals reach this parser; ordinary hostnames never trigger DNS.
            String literal = host.startsWith("[") && host.endsWith("]") ? host.substring(1, host.length() - 1) : host;
            if (!literal.matches("[0-9a-f:.]+")) throw new IllegalArgumentException(ADDRESS);
            final InetAddress address;
            try { address = InetAddress.getByName(literal); }
            catch (Exception ignored) { throw new IllegalArgumentException(ADDRESS); }
            if (address.isLoopbackAddress() || address.isAnyLocalAddress()) throw new IllegalArgumentException(PHONE);
        }
        if (scheme.equalsIgnoreCase("http") && !privateIpv4) {
            throw new IllegalArgumentException("Use HTTPS for a hosted server. Plain HTTP is allowed only for your computer's private Wi-Fi IPv4 address.");
        }
        return scheme.toLowerCase(Locale.ROOT) + "://" + host + (port == -1 ? "" : ":" + port);
    }

    private static boolean clipboardWhitespace(char value) {
        return Character.isWhitespace(value) || Character.isSpaceChar(value) || value == '\u200b' || value == '\ufeff';
    }

    private static String trimClipboardWhitespace(String value) {
        int start = 0, end = value.length();
        while (start < end && clipboardWhitespace(value.charAt(start))) start++;
        while (end > start && clipboardWhitespace(value.charAt(end - 1))) end--;
        return value.substring(start, end);
    }
}
