package app.phonelink.tracker;

import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

final class ApiClient {
    static final class ApiException extends Exception {
        final int status;
        ApiException(int status, String message) { super(message); this.status = status; }
    }

    static String normalizeServer(String value) throws Exception {
        return ServerAddress.normalize(value);
    }

    static JSONObject post(String server, String path, String token, JSONObject body) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(server + path).openConnection();
        connection.setRequestMethod("POST");
        connection.setInstanceFollowRedirects(false);
        connection.setConnectTimeout(8000);
        connection.setReadTimeout(8000);
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "application/json");
        if (token != null) connection.setRequestProperty("Authorization", "Bearer " + token);
        byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
        connection.setFixedLengthStreamingMode(bytes.length);
        try {
            try (OutputStream stream = connection.getOutputStream()) { stream.write(bytes); }
            int code = connection.getResponseCode();
            InputStream input = code >= 200 && code < 300 ? connection.getInputStream() : connection.getErrorStream();
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            if (input != null) {
                try (InputStream stream = input) {
                    byte[] chunk = new byte[2048]; int count;
                    while ((count = stream.read(chunk)) != -1) {
                        if (buffer.size() + count > 65536) throw new Exception("Unexpected server response.");
                        buffer.write(chunk, 0, count);
                    }
                }
            }
            JSONObject result;
            try { result = new JSONObject(new String(buffer.toByteArray(), StandardCharsets.UTF_8)); }
            catch (Exception ignored) { throw new ApiException(code, "Server returned an unexpected response. Check its address."); }
            if (code < 200 || code >= 300) throw new ApiException(code, result.optString("error", "Server error. Try again."));
            return result;
        } finally { connection.disconnect(); }
    }
}
