{
  description = "todolist-bot-discord distributed by Nix.";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          discordpy
          python-dotenv
        ]);
      in
      {
        packages.todolistbot = pkgs.stdenv.mkDerivation {
          pname = "todolistbot";
          version = "0.0.1";
          src = ./.;

          nativeBuildInputs = [ pkgs.makeWrapper ];
          buildInputs = [ pythonEnv pkgs.git ];

          dontBuild = true;

          installPhase = ''
            echo "Contents of source directory:"
            ls -la
            mkdir -p $out/bin $out/lib
            if [ -f "todolistbot.py" ]; then
              cp todolistbot.py $out/lib/
              makeWrapper ${pythonEnv}/bin/python $out/bin/todolistbot \
                --add-flags "$out/lib/todolistbot.py" \
                --prefix PATH : ${pkgs.git}/bin
            else
              echo "ERROR: todolistbot.py not found, adding it..."
              exit 1
            fi
          '';

          shellHook = ''
            export PATH=${pythonEnv}/bin:${pkgs.git}/bin:$PATH
          '';
        };

        defaultPackage = self.packages.${system}.todolistbot;

        defaultApp = {
          type = "app";
          program = "${self.packages.${system}.todolistbot}/bin/todolistbot";
        };
      });
}
