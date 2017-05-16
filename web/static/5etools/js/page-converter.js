

window.onload = loadparser

function loadparser() {
	// parse it on click
	$("input#parsestatblock").click(function() {
		var statblock = $("textarea#statblock").val().split("\n");
		var stats = {};

		for (var i = 0; i < statblock.length; i++) {
			var curline = statblock[i];

			// name of monster
			if (i === 0) {
				stats.name = curline.toLowerCase().replace(/\b\w/g, function(l){ return l.toUpperCase() });
				continue;
			}

			// size type alignment
			if (i === 1) {
				stats.size = curline[0];
				stats.type = curline.split(",")[0].split(" ").splice(1).join(" ") + ", " + $("input#source").val();
				stats.alignment = curline.split(", ")[1];
				continue;
			}

			// armor class
			if (i === 2) {
				stats.ac = curline.split("Armor Class ")[1];
				continue;
			}

			// hit points
			if (i === 3) {
				stats.hp = curline.split("Hit Points ")[1];
				continue;
			}

			// speed
			if (i === 4) {
				stats.speed = curline.split("Speed ")[1];
				continue;
			}

			if (i === 5) continue;
			// ability scores
			if (i === 6) {
				var abilities = curline.split(/ \((\+|\-|\–|\‒)?[0-9]*\) ?/g)
				stats.str = abilities[0];
				stats.dex = abilities[2];
				stats.con = abilities[4];
				stats.int = abilities[6];
				stats.wis = abilities[8];
				stats.cha = abilities[10];
				continue;
			}

			// saves (optional)
			if (!curline.indexOf("Saving Throws ")) {
				stats.save = curline.split("Saving Throws ")[1];
				continue;
			}

			// skills (optional)
			if (!curline.indexOf("Skills ")) {
				stats.skill = [curline.split("Skills ")[1]];
				continue;
			}

			// damage resistances (optional)
			if (!curline.indexOf("Damage Resistances ")) {
				stats.resist = curline.split("Resistances ")[1];
				continue;
			}

			// damage immunities (optional)
			if (!curline.indexOf("Damage Immunities ")) {
				stats.immune = curline.split("Immunities ")[1];
				continue;
			}

			// condition immunities (optional)
			if (!curline.indexOf("Condition Immunities ")) {
				stats.conditionImmune = curline.split("Immunities ")[1];
				continue;
			}

			// senses
			if (!curline.indexOf("Senses ")) {
				stats.senses = curline.split("Senses ")[1].split(" passive Perception ")[0];
				if (!stats.senses.indexOf("passive Perception")) stats.senses = "";
				if (stats.senses[stats.senses.length-1] === ",") stats.senses = stats.senses.substring(0, stats.senses.length-1);
				stats.passive = curline.split(" passive Perception ")[1];
				continue;
			}

			// languages
			if (!curline.indexOf("Languages ")) {
				stats.languages = curline.split("Languages ")[1];
				continue;
			}

			// challenges and traits
			// goes into actions
			if (!curline.indexOf("Challenge ")) {
				stats.cr = curline.split("Challenge ")[1].split(" (")[0];

				// traits
				i++;
				curline = statblock[i];
				stats.trait = [];
				stats.action = [];
				stats.reaction = [];
				stats.legendary = [];

				function moveon(cur) {
					return (!curline.toUpperCase().indexOf("ACTIONS") || !curline.toUpperCase().indexOf("LEGENDARY ACTIONS") || !curline.toUpperCase().indexOf("REACTIONS"))
				}

				var curtrait = {};

				var ontraits = true;
				var onactions = false;
				var onreactions = false;
				var onlegendaries = false;
				var onlegendarydescription = false;

				// keep going through traits til we hit actions
				while (i < statblock.length) {
					if (moveon(curline)) {
						ontraits = false;
						onactions = !curline.toUpperCase().indexOf("ACTIONS")
						onreactions = !curline.toUpperCase().indexOf("REACTIONS")
						onlegendaries = !curline.toUpperCase().indexOf("LEGENDARY ACTIONS")
						onlegendarydescription = onlegendaries;

						i++;
						curline = statblock[i];
					}

					// get the name
					curtrait.name = "";
					curtrait.text = []

					if (!onlegendarydescription) {
						// first pargraph
						curtrait.name = curline.split(/(\.|\!)/g)[0];
						curtrait.text.push(curline.split(".").splice(1).join("."));
					} else {
						curtrait.text.push(curline);
						onlegendarydescription = false;
					}

					i++;
					curline = statblock[i];

					// get paragraphs
					while (curline && curline.match(/^([A-Zot][a-z\'\’\`]+( \(.*\)| )?)+(\.|\!)+/g) === null && !moveon(curline)) {
						curtrait.text.push(curline);
						i++;
						curline = statblock[i];
					};

					if (ontraits) stats.trait.push(curtrait);
					if (onactions) stats.action.push(curtrait);
					if (onreactions) stats.reaction.push(curtrait);
					if (onlegendaries) stats.legendary.push(curtrait);
					curtrait = {};
				}


			}

		}


		$("textarea#output").text(JSON.stringify (stats, null, " "));
	})
}
