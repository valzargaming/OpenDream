using System.Text;

namespace OpenDreamShared.Dream;

public static class StringFormatDecoder {
    private static readonly ushort FormatPrefix = 0xFF00;

    /// <returns>The input if unformatted, otherwise a string with formatting removed.</returns>
    public static string RemoveFormatting(string input) {
        var firstFormat = -1;
        for (var i = 0; i < input.Length; i++) {
            if ((input[i] & FormatPrefix) == FormatPrefix) {
                firstFormat = i;
                break;
            }
        }

        // Default JSON escaping means serialized savefile text takes this path.
        if (firstFormat == -1)
            return input;

        // Local lifetime: do not retain the largest formatted input forever.
        var result = new StringBuilder(input.Length);
        result.Append(input, 0, firstFormat);
        for (var i = firstFormat + 1; i < input.Length; i++) {
            if ((input[i] & FormatPrefix) != FormatPrefix)
                result.Append(input[i]);
        }
        return result.ToString();
    }
}
