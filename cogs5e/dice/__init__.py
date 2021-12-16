from .cog import Dice


def setup(bot):
    bot.add_cog(Dice(bot))
