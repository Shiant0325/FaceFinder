using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class Program
{
    [STAThread]
    private static int Main()
    {
        try
        {
            string installRoot = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
            string pythonw = Path.Combine(installRoot, "runtime", "pythonw.exe");
            string launcher = Path.Combine(installRoot, "launcher.pyw");
            if (!File.Exists(pythonw) || !File.Exists(launcher))
            {
                MessageBox.Show(
                    "FaceFinder runtime files are missing. Run FaceFinder_Setup.exe again to repair the installation.",
                    "FaceFinder",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return 2;
            }

            string dataRoot = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "FaceFinder");
            Directory.CreateDirectory(dataRoot);

            var start = new ProcessStartInfo
            {
                FileName = pythonw,
                Arguments = "\"" + launcher + "\"",
                WorkingDirectory = installRoot,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            start.EnvironmentVariables["FACEFINDER_INSTALL_DIR"] = installRoot;
            start.EnvironmentVariables["FACEFINDER_DATA_DIR"] = dataRoot;
            start.EnvironmentVariables["FACEFINDER_MODEL_DIR"] = Path.Combine(installRoot, "data", "insightface");
            start.EnvironmentVariables["INSIGHTFACE_HOME"] = Path.Combine(installRoot, "data", "insightface");
            Process.Start(start);
            return 0;
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.ToString(), "FaceFinder could not start", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
