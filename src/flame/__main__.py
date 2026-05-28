import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "export-transmission":
        if len(argv) not in (2, 3):
            raise SystemExit("Usage: python -m flame export-transmission <in.h5> [out.txt]")
        from flame.hdfdata import HdfData

        in_path = argv[1]
        if len(argv) == 3:
            out_path = argv[2]
        else:
            import os

            base = os.path.splitext(os.path.basename(in_path))[0]
            parts = base.split("-")
            if len(parts) >= 2:
                out_base = "{}_{}".format(parts[1], parts[-1])
            else:
                out_base = base
            out_path = os.path.join(os.path.dirname(in_path), out_base + "_transmission.txt")

        HdfData.export_transmission_columns(in_path, out_path)
        return

    from flame.gui import main as gui_main

    gui_main()


if __name__ == "__main__":
    main()
