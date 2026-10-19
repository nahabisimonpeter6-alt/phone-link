package app.phonelink.tracker;

/** Host-side regressions for addresses copied from browsers and entered on a physical phone. */
public final class ServerAddressSmoke {
    private static int checks;

    private static void accepts(String input, String expected) {
        String actual = ServerAddress.normalize(input);
        if (!expected.equals(actual)) throw new AssertionError("Unexpected normalized origin: " + actual);
        checks++;
    }

    private static void rejects(String input, String messagePart) {
        try { ServerAddress.normalize(input); }
        catch (IllegalArgumentException error) {
            String message = error.getMessage();
            if (message == null || !message.contains(messagePart)) {
                throw new AssertionError("Expected a helpful validation message containing: " + messagePart, error);
            }
            if (message.contains("private-key-marker") || message.contains("authority at index") || message.contains("URISyntaxException")) {
                throw new AssertionError("Parser details or pasted input leaked into error", error);
            }
            checks++;
            return;
        }
        throw new AssertionError("Invalid server address was accepted");
    }

    public static void main(String[] args) {
        accepts("https://owner.pythonanywhere.com", "https://owner.pythonanywhere.com");
        accepts(" HTTPS://OWNER.PYTHONANYWHERE.COM/\n", "https://owner.pythonanywhere.com");
        accepts("\u00a0\u202fhttps://owner.pythonanywhere.com/\u00a0", "https://owner.pythonanywhere.com");
        accepts("\u200b\ufeffhttps://owner.pythonanywhere.com\ufeff\u200b", "https://owner.pythonanywhere.com");
        accepts("https://example.com:443/", "https://example.com:443");
        accepts("https://example.com:1", "https://example.com:1");
        accepts("https://example.com:65535", "https://example.com:65535");
        accepts("http://192.168.1.10:8080/", "http://192.168.1.10:8080");
        accepts("HTTP://10.10.0.113:8080", "http://10.10.0.113:8080");
        accepts("http://172.16.0.1", "http://172.16.0.1");
        accepts("http://172.31.255.254", "http://172.31.255.254");
        accepts("https://8.8.8.8", "https://8.8.8.8");
        accepts("HTTPS://[2001:DB8::1]:8443/", "https://[2001:db8::1]:8443");

        rejects("http://\u00a0localhost:8080", "Remove spaces");
        rejects("https://owner.\u202fpythonanywhere.com", "Remove spaces");
        rejects("https://example.com/\tprivate-key-marker", "Remove spaces");
        rejects("https://exam\u200bple.com", "Remove spaces");
        rejects("[https://example.com](https://example.com)", "Enter only");
        rejects("https://example.com/[private-key-marker]", "Enter only");
        rejects("https://user:private-key-marker@example.com", "Enter only");
        rejects("https://example.com/dashboard", "Enter only");
        rejects("https://example.com//", "Enter only");
        rejects("https://example.com/%2f", "Enter only");
        rejects("https://example.com?key=private-key-marker", "Enter only");
        rejects("https://example.com#private-key-marker", "Enter only");
        rejects("example.com", "must start with");
        rejects("ftp://example.com", "must start with");
        rejects("", "Enter only");
        rejects(null, "Enter only");
        rejects("\u00a0\u200b\t", "Enter only");
        rejects("https://example.com:0", "port between");
        rejects("https://example.com:65536", "port between");
        rejects("https://example.com:999999", "port between");
        rejects("https://example.com:", "port between");
        rejects("https://example.com:-1", "Enter only");
        rejects("https://example.com:abc", "Enter only");
        rejects("https://example.com:999999999999999999999999", "Enter only");

        for (String host : new String[]{"localhost", "LOCALHOST", "localhost.", "tracker.localhost", "127.0.0.1", "127.10.2.3",
                "0.0.0.0", "0", "127", "2130706433", "[::1]", "[0:0:0:0:0:0:0:1]", "[::]",
                "[0:0:0:0:0:0:0:0]", "[::ffff:127.0.0.1]", "[::ffff:0.0.0.0]"}) {
            rejects("http://" + host + ":8080", "points to this phone");
            rejects("https://" + host, "points to this phone");
        }
        for (String host : new String[]{"example.com", "8.8.8.8", "172.15.255.254", "172.32.0.1", "192.169.0.1", "169.254.1.2", "[2001:db8::1]"}) {
            rejects("http://" + host, "Use HTTPS");
        }
        rejects("http://192.168.001.1:8080", "Enter only");
        rejects("http://127.1:8080", "Enter only");
        rejects("https://0x7f000001", "Enter only");
        rejects("https://0x7f.0.0.1", "Enter only");
        rejects("https://017700000001", "Enter only");
        rejects("http://256.1.1.1:8080", "Enter only");
        rejects("http://[fe80::1%25eth0]", "Enter only");
        System.out.println("Android server-address checks passed: " + checks);
    }
}
